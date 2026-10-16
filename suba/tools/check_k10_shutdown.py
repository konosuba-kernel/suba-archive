#!/usr/bin/env python3
"""K10 exploratory power state machine: patch only a new isolated build snapshot.

Production remains frozen for K8/K9. Success requires guest SBI shutdown (and a
real same-QEMU cold reset for reboot), never a host terminate/quit action.
"""
import argparse
import json
import re
import hashlib
import struct
from pathlib import Path
import select
import shutil
import socket
import subprocess
import time
import kernel_probe
from PIL import Image
from check_kernel_entry import require
from check_k2 import sha
from mkfs import format_disk
from read_disk import Disk
ROOT = Path(__file__).resolve().parents[1]


def prototype(out, guarded=True):
    def change(name, old, new):
        path = out / name
        text = path.read_text()
        require(text.count(old) == 1, 'power prototype anchor: ' + name)
        path.write_text(text.replace(old, new))
    shutil.copyfile(ROOT / 'tests/k10/power_dispatch.vt', out / 'kernel/dispatch_power.vt')
    change('kernel/kernel.build', 'source kernel/dispatch.vt',
           'source kernel/dispatch.vt\nsource kernel/dispatch_power.vt')
    change('kernel/objects.vt', 'pub const PREPARE: u32 = 16;',
           'pub const PREPARE: u32 = 16;\npub const POWER: u32 = 32;')
    change('kernel/dispatch_window.vt', 'objects::READ | objects::KILL);',
           'objects::READ | objects::KILL | objects::POWER);')
    change('kernel/dispatch_call.vt', '        let operation: usize = signal.value;',
           '''        let operation: usize = signal.value;
        if operation == abi::SYS_POWER { return power_call(id, args); }
        if stopping() && power_write(operation, args) { return answer(id, abi::DENIED, 0); }''')
    if guarded:
        change('kernel/dispatch.vt',
            '        if !request::active(work.owner, work.token) { return true; }',
            '        if !request::active(work.owner, work.token) { return true; }\n'
            '        if stopping() && !process::trusted_desktop(work.owner) { return true; }')
    # A separate owner action authorizes the otherwise forbidden desktop death.
    with (out / 'kernel/process_display.vt').open('a') as target:
        target.write('''
// Kernel shutdown coordinator only. Ordinary terminate retains desktop protection.
pub unsafe fn shutdown_desktop(id: Id) -> bool {
    unsafe {
        if !valid(id) || !trusted_desktop(id) { return false; }
        RECORDS[id.slot].state = State::Dying;
        RECORDS[id.slot].status = abi::CANCELLED;
        RECORDS[id.slot].loading = Loading::Empty;
        return true;
    }
}
''')
    # Borrowed ramfb leaves must be removed before the allocator-owned page reap.
    change('kernel/process_display.vt',
        '            Desktop::Trusted(value) => { return space::Progress::Invalid; }\n        }\n        match RECORDS[id.slot].space {\n            AddressSpace::Empty => { return space::Progress::Invalid; },',
        '''            Desktop::Trusted(value) => {
                if value.slot != id.slot || value.generation != id.generation ||
                    state_code(RECORDS[id.slot].state) != state_code(State::Dying) { return space::Progress::Invalid; }
            }
        }
        match RECORDS[id.slot].space {
            AddressSpace::Empty => { return space::Progress::Invalid; },''')
    change('kernel/process.vt',
        '        if !valid(id) || state_code(RECORDS[id.slot].state) != state_code(State::Dying) { return space::Progress::Invalid; }',
        '''        if !valid(id) || state_code(RECORDS[id.slot].state) != state_code(State::Dying) { return space::Progress::Invalid; }
        if trusted_desktop(id) {
            match abort_display_step(id) {
                space::Progress::Invalid => { return space::Progress::Invalid; },
                space::Progress::More => { return space::Progress::More; },
                space::Progress::Done => {}
            }
        }''')
    change('kernel/fs/worker.vt',
        '            RequestState::Done(result) => { OPERATIONS[0_usize].state = RequestState::Empty; return Progress::Ready; },',
        '''            RequestState::Done(result) => {
                match result {
                    Outcome::Value(value) => {
                        if value != 0_usize { return Progress::Invalid; }
                        OPERATIONS[0_usize].state = RequestState::Empty;
                        return Progress::Ready;
                    },
                    Outcome::Failed(error) => {}, Outcome::File(id) => {}, Outcome::Directory(node) => {}
                }
                return Progress::Invalid;
            },''')
    with (out / 'kernel/machine_runtime.vt').open('a') as target:
        target.write('''
extern abi(C) fn __suba_power_reset(action: usize) -> usize;
// SBI SRST:0 shutdown,1 cold reboot. Every returned value is failure.
pub fn power_reset(action: usize) -> bool {
    unsafe { let error: usize = __suba_power_reset(action); }
    return false;
}
''')
    text = (out / 'kernel/trap.s0').read_text()
    reset = text[text.index('__suba_power_off:'):].replace('__suba_power_off:', '__suba_power_reset:').replace('addi x10, x0, 0\n', '', 1)
    with (out / 'kernel/trap.s0').open('a') as target:
        target.write('\n# C a0 supplies a validated SRST reset_type; preserves x27 and stack.\n' + reset)
    change('kernel/entry.vt', '        dispatch::sources(IMAGES);',
           '        dispatch::sources(IMAGES);\n        dispatch::power_baseline(memory::stats().free);')
    change('kernel/entry.vt', '                slices = slices + 1_usize;', '''                match dispatch::power_step() {
                    dispatch::PowerStep::Running => {}, dispatch::PowerStep::Wait => {},
                    dispatch::PowerStep::More => { storage_work = true; },
                    dispatch::PowerStep::Invalid => { storage_failure("power"); let stopped: u32 = panic(74); return 0; },
                    dispatch::PowerStep::Ready => {
                        machine::text("power: flushed action="); dispatch::number(dispatch::power_action()); machine::text("\\n");
                        let returned: bool = machine::power_reset(dispatch::power_action());
                        let stopped: u32 = panic(75); return 0;
                    }
                }
                slices = slices + 1_usize;''')


def busy_observer(out, loading=False, force_order=False):
    """Hold the real second output DMA until the authorized power call accepts it."""
    def change(name, old, new):
        p = out / name
        s = p.read_text()
        require(s.count(old) == 1, 'power DMA observer anchor ' + name)
        p.write_text(s.replace(old, new))
    change('kernel/fs/state.vt', 'module kernel::fs;',
           'module kernel::fs;\nimport kernel::device::hub;')
    with (out / 'kernel/device/hub.vt').open('a') as p:
        p.write('''
// TEST ONLY: defer a real device IRQ; never fabricate or consume used entries.
pub unsafe fn power_test_hold() -> () {
    unsafe { io::write32(devices::MMIO_OFFSET + devices::PLIC_ENABLE + 0x80_usize, 0); }
    return ();
}
pub unsafe fn power_test_release() -> () {
    unsafe { io::write32(devices::MMIO_OFFSET + devices::PLIC_ENABLE + 0x80_usize, ENABLED); }
    return ();
}
''')
    with (out / 'kernel/fs/worker.vt').open('a') as p:
        p.write('''
static mut POWER_TEST_ARMED: bool = false;
static mut POWER_TEST_HELD: bool = false;
pub unsafe fn power_test_arm() -> bool {
    unsafe { if POWER_TEST_ARMED { return false; } POWER_TEST_ARMED = true; return true; }
}
unsafe fn power_test_submit() -> () {
    unsafe {
        if POWER_TEST_ARMED && !POWER_TEST_HELD && OPERATIONS[ACTIVE].client.slot != 0_usize {
            POWER_TEST_HELD = true;
            hub::power_test_hold();
        }
    }
    return ();
}
pub unsafe fn power_test_stage() -> usize {
    unsafe {
        if !POWER_TEST_HELD || ACTIVE == 16_usize || !SUBMITTED { return 0; }
        match block::state() {
            block::State::Submitted => { return 1; }, block::State::Idle => {},
            block::State::Completed => {}, block::State::Offline => {}, block::State::Failed => {}
        }
        return 0;
    }
}
pub unsafe fn power_test_release() -> bool {
    unsafe {
        if !POWER_TEST_ARMED { return true; }
        if power_test_stage() != 1_usize { return false; }
        POWER_TEST_ARMED = false;
        hub::power_test_release();
        return true;
    }
}
''')
    if loading:
        anchor = '        if IO_INDEX >= BLOCK_COUNT || !block::submit(block::Command::Read(DISK_BASE + BLOCK_IDS[IO_INDEX] as usize))'
        change('kernel/fs/transfer.vt', anchor,
               '        if OFFSET != 0_usize { power_test_submit(); }\n' + anchor)
    else:
        anchor = '        if !block::submit(block::Command::Write(DISK_BASE + BLOCK_IDS[IO_INDEX] as usize))'
        change('kernel/fs/transfer.vt', anchor,
               '        if IO_INDEX == 1_usize { power_test_submit(); }\n' + anchor)
    anchor = '        if operation == abi::SYS_STATS {'
    change('kernel/dispatch_call.vt', anchor, anchor + '''
            if args[0_usize] == 1000_usize { return answer(id, abi::OK, fs::power_test_stage()); }
            if args[0_usize] == 1001_usize {
                if !fs::power_test_arm() { return false; }
                return answer(id, abi::OK, 0);
            }
''')
    if loading:
        with (out / 'kernel/dispatch_power.vt').open('a') as p:
            p.write("""
// TEST ONLY: ensure the suspended request really owns a lower-slot Loading child.
unsafe fn power_test_loading() -> bool {
    unsafe {
        var slot: usize = 1;
        while slot < process::CAPACITY {
            match request::peek(slot) {
                request::Peek::Empty => {}, request::Peek::Ready(work) => {
                    match work.operation {
                        request::Operation::Loading(value) => {
                            if process::slot(value.child) >= process::slot(work.owner) { return false; }
                            machine::text("power test: loading child="); number(process::slot(value.child));
                            machine::text(" parent="); number(process::slot(work.owner)); machine::text("\\n");
                            return true;
                        },
                        request::Operation::Idle => {}, request::Operation::Job(v) => {},
                        request::Operation::File(v) => {}, request::Operation::Read(v) => {},
                        request::Operation::Write(v) => {}, request::Operation::Wait(v) => {},
                        request::Operation::Preparing(v) => {}, request::Operation::Installing(v) => {},
                        request::Operation::Pages(v) => {}, request::Operation::WindowCreate(v) => {},
                        request::Operation::WindowCopy(v) => {}
                    }
                }
            }
            slot = slot + 1_usize;
        }
    }
    return false;
}
""")
        change('kernel/dispatch_power.vt', '        POWER_ACTION = args[1_usize];',
            '        if fs::power_test_stage() == 1_usize && !power_test_loading() { return false; }\n'
            '        POWER_ACTION = args[1_usize];')
    if force_order:
        require(loading, 'forced order requires the Loading observer')
        with (out / 'kernel/dispatch_power.vt').open('a') as p:
            p.write('\nstatic mut POWER_TEST_CHILD: usize = 16;\nstatic mut POWER_TEST_PARENT: usize = 16;\n')
        change('kernel/dispatch_power.vt',
            '                            machine::text("power test: loading child=");',
            '                            POWER_TEST_CHILD = process::slot(value.child);\n'
            '                            POWER_TEST_PARENT = process::slot(work.owner);\n'
            '                            machine::text("power test: loading child=");')
        change('kernel/dispatch_power.vt',
            '                    if !stop_ordinary(slot) { return PowerStep::Invalid; }',
            """                    if !stop_ordinary(slot) { return PowerStep::Invalid; }
                    // TEST ONLY: choose an allowed next dispatch slot after the child dies.
                    // No process state, request, completion, or IRQ is fabricated.
                    if slot == POWER_TEST_CHILD {
                        CURSOR = POWER_TEST_PARENT;
                        POLL_CHILD = true;
                        POLL_WINDOW = true;
                        POWER_TEST_CHILD = 16;
                        machine::text("power test: next ordinary dispatch is Loading parent\\n");
                    }""")
    anchor = '        POWER_ACTION = args[1_usize];' 
    change('kernel/dispatch_power.vt', anchor, '''        if fs::power_test_stage() == 1_usize { machine::text("power test: submitted DMA at accepted request\\n"); }
        if !fs::power_test_release() { return false; }
''' + anchor)


def programs():
    sources = ['abi/contract.vt', 'abi/syscalls.vt', 'abi/files.vt', 'abi/argument_wire.vt',
        'user/libsuba/syscall.vt', 'user/libsuba/arguments.vt', 'user/libsuba/argument_builder.vt',
        'user/libsuba/services.vt', 'user/libsuba/files.vt', 'tests/k10/power_user.vt']
    return [dict(entry='test::power::' + entry, sources=sources,
                 assembly=['user/libsuba/syscall.s0']) for entry in ('start', 'worker')]


def run(out, command, reboot, fault):
    command = [x for x in command if x not in ('-nographic', '-no-reboot')]
    command += ['-display', 'none', '-serial', 'file:' + str(out / 'serial.log'), '-monitor', 'none',
                '-qmp', 'unix:' + str(out / 'qmp.sock') + ',server=on,wait=off']
    record = dict(passed=False, command=command, events=[], host_terminated=False)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    began = time.monotonic()
    qmp = None
    try:
        while not (out / 'qmp.sock').exists():
            require(process.poll() is None and time.monotonic() - began < 15, 'QMP startup')
            time.sleep(.05)
        qmp = socket.socket(socket.AF_UNIX)
        qmp.connect(str(out / 'qmp.sock'))
        qmp.sendall(b'{"execute":"qmp_capabilities"}\n')
        pending = b''
        last_frame = 0.0
        expected_failure = False
        while process.poll() is None and time.monotonic() - began < 60:
            if time.monotonic() - last_frame > .5:
                qmp.sendall((json.dumps({'execute': 'screendump', 'arguments': {'filename': str(out / 'frame.ppm')}, 'id': 'frame'}) + '\n').encode())
                last_frame = time.monotonic()
            if select.select([qmp], [], [], .05)[0]:
                chunk = qmp.recv(65536)
                if not chunk:
                    break
                pending += chunk
                while b'\n' in pending:
                    line, pending = pending.split(b'\n', 1)
                    event = json.loads(line)
                    record['events'].append(event)
                    if event.get('id') == 'frame' and 'return' in event:
                        pixel = Image.open(out / 'frame.ppm').getpixel((0, 0))
                        require(pixel[0] != 255, 'power U fixture failed: ' + str(pixel[2]))
            log = (out / 'serial.log').read_text() if (out / 'serial.log').exists() else ''
            if 'panic' in log.lower():
                require(fault != 'none' and 'power: processes drained' in log and 'power: flushed' not in log,
                        'unexpected power failure: ' + log[-2500:])
                lines = [line for line in log.splitlines() if line.startswith('block failure ')]
                require(len(lines) == 1, 'missing exact block failure tuple')
                fields = dict(re.findall(r'(\w+)=([\w.]+)', lines[0]))
                require(fields['command'] == '4' and fields['state'] == 'submitted', 'not the final Flush')
                if fault == 'timeout':
                    require(fields['reason'] == '7' and fields['used'] == fields['consumed'] and
                            fields['status'] == '255' and int(fields['observed']) - int(fields['began']) > 10000000,
                            'wrong final Flush timeout')
                else:
                    require(fields['reason'] == '6' and fields['status'] == '1' and
                            int(fields['used']) == int(fields['consumed']) + 1, 'wrong final Flush EIO')
                record['expected_failure'] = fields
                expected_failure = True
                break
        if expected_failure:
            require(not any(e.get('event') == 'SHUTDOWN' for e in record['events']), 'failed Flush shut down anyway')
            record['passed'] = True
            record['sbi_success'] = False
            return record
        require(fault == 'none', 'injected final Flush failure was not observed')
        record['exit'] = process.wait(timeout=3)
        log = (out / 'serial.log').read_text()
        require(record['exit'] == 0 and 'power: flushed action=0' in log, 'guest did not power off after flush')
        shutdown = [e for e in record['events'] if e.get('event') == 'SHUTDOWN']
        require(any(e['data'].get('guest') for e in shutdown), 'no guest-origin QMP shutdown')
        if reboot:
            require('power: flushed action=1' in log and 'suba K4: mounted boot=2' in log, 'missing cold reboot/persistent reread')
            require(any(e.get('event') == 'RESET' and e['data'].get('guest') for e in record['events']), 'no guest-origin QMP reset')
        record['passed'] = True
        record['sbi_success'] = True
    finally:
        if process.poll() is None:
            record['host_terminated'] = True
            process.terminate()
        _, stderr = process.communicate(timeout=5)
        if qmp:
            qmp.close()
        record['elapsed'] = time.monotonic() - began
        (out / 'stderr.log').write_bytes(stderr)
        (out / 'run.json').write_text(json.dumps(record, indent=2) + '\n')
    return record


def disk_ledger(path, contract):
    disk = Disk(path, contract)
    c = disk.c
    blocks = sum(struct.unpack_from('<I', disk.data,
                 c['FS_FAT_START'] * c['BLOCK_BYTES'] + i * 4)[0] != 0
                 for i in range(c['FS_DATA_START'], c['FS_BLOCKS']))
    files = {name: hashlib.sha256(disk.read(name)).hexdigest()
             for name, index in disk.paths.items() if disk.nodes[index]['kind'] == c['NODE_FILE']}
    return dict(nodes=len(disk.nodes), blocks=blocks, files=files,
                flagged=sum(node['flags'] != 0 for node in disk.nodes.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--kernel-from', type=Path)
    parser.add_argument('--fault', choices=['none', 'eio', 'timeout'], default='none')
    parser.add_argument('--scenario', choices=['basic', 'busy', 'loading'], default='basic')
    parser.add_argument('--action', choices=['shutdown', 'reboot'], default='shutdown')
    parser.add_argument('--force-order', action='store_true', help='test-only: select Loading parent immediately after child termination')
    parser.add_argument('--production', action='store_true', help='snapshot current power implementation without prototype mutation')
    parser.add_argument('--unguarded', action='store_true', help='negative control: permit pending spawn advance during stop')
    args = parser.parse_args()
    out, compiler = args.out.resolve(), args.compiler.resolve()
    prefix = 'k10-power-' if args.production else 'k10-power-prototype'
    require(out.name.startswith(prefix), 'power evidence directory must start with ' + prefix)
    record = dict(passed=False, exploratory=True, compiler_sha256=sha(compiler), source_inputs=kernel_probe.snapshot(out))
    shutil.copyfile(Path(__file__), out / 'probe.py')
    record['probe_sha256'] = sha(out / 'probe.py')
    try:
        require(not (args.production and args.unguarded), 'production cannot remove its stop guard')
        require(not args.force_order or args.scenario == 'loading', 'forced order needs loading scenario')
        if args.production:
            require((out / 'kernel/dispatch_power.vt').is_file(), 'production power module missing')
        else:
            prototype(out, not args.unguarded)
        record.update(scenario=args.scenario, fault=args.fault, action=args.action, guarded=not args.unguarded,
                      production=args.production, exploratory=not args.production, force_order=args.force_order)
        if args.scenario != 'basic':
            busy_observer(out, args.scenario == 'loading', args.force_order)
            record['observer'] = ('real image DMA held with Loading child below parent' if args.scenario == 'loading' else
                'real output DMA held until power request; frozen Job and stream-blocked process')
        command = kernel_probe.build(compiler, out, programs(), record, args.kernel_from.resolve() if args.kernel_from else None)
        tree = out / 'initial'
        for directory in ('sys', 'work', 'jobs'):
            (tree / directory).mkdir(parents=True)
        shutil.copyfile(out / 'build/user1.elf', tree / 'sys/worker')
        (tree / 'work/mode').write_bytes({'basic': b'0', 'busy': b'1', 'loading': b'2'}[args.scenario])
        (tree / 'work/action').write_bytes(b'1' if args.action == 'reboot' else b'0')
        record['initial_disk'] = format_disk(tree, out / 'disk.raw', out / 'abi/contract.vt')
        before = disk_ledger(out / 'disk.raw', out / 'abi/contract.vt')
        command += ['-global', 'virtio-mmio.force-legacy=false', '-device', 'virtio-keyboard-device',
            '-device', 'virtio-tablet-device', '-drive', f'file={out}/disk.raw,if=none,format=raw,id=blk,cache=writeback',
            '-device', 'virtio-blk-device,drive=blk']
        if args.fault != 'none':
            config = out / 'blkdebug.conf'
            config.write_text('[set-state]\nevent = "flush_to_disk"\nstate = "1"\nnew_state = "2"\n'
                '[inject-error]\nevent = "flush_to_disk"\niotype = "flush"\nstate = "2"\n'
                + ('errno = "5"\n' if args.fault == 'eio' else 'errno = "0"\ndelay-ns = "1200000000"\n')
                + 'once = "on"\n')
            command[command.index('-drive') + 1] = (f'file=blkdebug:{config}:{out}/disk.raw,'
                'if=none,format=raw,id=blk,cache=writeback,rerror=report,werror=report')
        record['result'] = run(out, command, args.action == 'reboot', args.fault)
        if args.fault == 'none':
            after = disk_ledger(out / 'disk.raw', out / 'abi/contract.vt')
            expected = dict(before['files'])
            expected['/work/saved'] = hashlib.sha256(b'survived').hexdigest()
            extra = 1
            if args.scenario == 'loading':
                expected['/work/go'] = hashlib.sha256(b'1').hexdigest()
                extra = 2
            require(after['files'] == expected, 'persistent file bytes/namespace changed')
            require(after['nodes'] == before['nodes'] + extra and
                    after['blocks'] == before['blocks'] + extra and after['flagged'] == 0,
                    'shutdown leaked temporary node/block ownership')
            record['disk_ledger'] = dict(before=before, after=after)
        record['passed'] = True
    except Exception as error:
        record['error'] = str(error)
        raise
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')


if __name__ == '__main__':
    main()
