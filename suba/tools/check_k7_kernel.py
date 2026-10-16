#!/usr/bin/env python3
"""Real FS image/Job/publication probes on an unmodified frozen production kernel.

The designated trusted U test desktop reports a result through its ordinary
framebuffer grant. Its children use normal FS spawn. Host builds initial files,
reads QMP screenshots and stops only after the guest's bounded assertions finish.
"""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import time
from PIL import Image
import kernel_probe
from check_k2 import sha
from check_kernel_entry import FIRMWARE, require
from check_k5_devices import Qmp
from mkfs import format_disk
ROOT = Path(__file__).resolve().parents[1]


def observe_cancel(out, without_user_irq=False):
    """Hold a real DMA submission until the U parent cancels, then require U IRQ.

    Instrumentation changes only scheduling/observability of frozen test sources;
    it never fabricates used entries, FS results, kill actions or cleanup.
    """
    def change(name, anchor, replacement):
        path = out / name
        text = path.read_text()
        require(text.count(anchor) == 1, 'K7 observer anchor: ' + name)
        path.write_text(text.replace(anchor, replacement))
    change('kernel/fs/state.vt', 'module kernel::fs;',
           'module kernel::fs;\nimport kernel::device::hub;')
    path = out / 'kernel/device/hub.vt'
    path.write_text(path.read_text() + '''
// TEST ONLY: real PLIC submission hold and actual U external trap ledger.
static mut TEST_RELEASE: bool = false;
static mut TEST_EXPECT: bool = false;
static mut TEST_BASE: usize = 0;
static mut TEST_SEEN: usize = 0;
pub unsafe fn test_pause() -> () {
    unsafe { io::write32(devices::MMIO_OFFSET + devices::PLIC_ENABLE + 0x80_usize, 0); }
    return ();
}
pub unsafe fn test_release() -> () { unsafe { TEST_RELEASE = true; } return (); }
pub unsafe fn test_seen() -> usize { unsafe { return TEST_SEEN; } }
pub unsafe fn test_before_user() -> () {
    unsafe {
        if TEST_RELEASE {
            TEST_RELEASE = false; TEST_EXPECT = true; TEST_BASE = USER_TRAPS;
            io::write32(devices::MMIO_OFFSET + devices::PLIC_ENABLE + 0x80_usize, ENABLED);
            io::write32(devices::MMIO_OFFSET + devices::PLIC_CONTEXT, 0);
        }
    }
    return ();
}
''')
    anchor = '            if source == BLOCK_IRQ { if !block::interrupt()'
    change('kernel/device/hub.vt', anchor,
           '            if TEST_EXPECT { TEST_EXPECT = false; TEST_SEEN = TEST_SEEN + 1_usize; }\n' + anchor)
    anchor = 'pub unsafe fn service() -> bool {\n    unsafe {'
    change('kernel/device/hub.vt', anchor,
           anchor + '\n        if TEST_EXPECT && USER_TRAPS <= TEST_BASE { return true; }')
    anchor = '                    machine::activate(selected.token);'
    change('kernel/entry.vt', anchor, '                    hub::test_before_user();\n' + anchor)
    if without_user_irq:
        path = out / 'kernel/trap.s0'
        text = path.read_text()
        require(text.count('addi x5, x0, 544') == 2, 'U external interrupt enable anchors')
        path.write_text(text.replace('addi x5, x0, 544', 'addi x5, x0, 32'))
    path = out / 'kernel/fs/worker.vt'
    path.write_text(path.read_text() + '''
// TEST ONLY: reports the real submitted phase. No synthesized completion.
static mut TEST_KIND: usize = 0;
static mut TEST_HELD: bool = false;
pub unsafe fn test_arm(kind: usize) -> bool {
    unsafe { if TEST_HELD { return false; } TEST_KIND = kind; return true; }
}
unsafe fn test_submit(kind: usize) -> () {
    unsafe {
        if TEST_KIND == kind && !TEST_HELD && OPERATIONS[ACTIVE].client.slot != 0_usize {
            TEST_HELD = true;
            hub::test_pause();
        }
    }
    return ();
}
pub unsafe fn test_stage() -> usize {
    unsafe {
        if !TEST_HELD || ACTIVE == 16_usize || !SUBMITTED { return 0; }
        match block::state() { block::State::Submitted => { return 1; },
            block::State::Idle => {}, block::State::Completed => {}, block::State::Offline => {}, block::State::Failed => {} }
        return 0;
    }
}
pub unsafe fn test_release() -> bool {
    unsafe {
        if test_stage() != 1_usize { return false; }
        TEST_KIND = 0;
        hub::test_release();
        return true;
    }
}
pub unsafe fn test_seen() -> usize {
    unsafe {
        if TEST_HELD && test_stage() == 0_usize { TEST_HELD = false; }
        return hub::test_seen();
    }
}
''')
    # Read loader cancellation occurs in child actor slot1; its own image is read
    # by controller slot0 and cannot accidentally satisfy this predicate.
    anchor = 'unsafe fn submit_read() -> Progress {\n    unsafe {'
    change('kernel/fs/transfer.vt', anchor, anchor + '\n        if OFFSET != 0_usize { test_submit(1); }')
    anchor = '        if !block::submit(block::Command::Write(DISK_BASE + BLOCK_IDS[IO_INDEX] as usize))'
    change('kernel/fs/transfer.vt', anchor, '        if IO_INDEX == 1_usize { test_submit(2); }\n' + anchor)
    anchor = '                                if !process::terminate(target, abi::CANCELLED)'
    change('kernel/dispatch_call.vt', anchor, '''                                if !fs::test_release() { return false; }
                                machine::text("K7 observed submitted FS load cancel\\n");
''' + anchor)
    anchor = '                            fs::end_domain(job);'
    change('kernel/dispatch_jobs.vt', anchor, '''                            if !fs::test_release() { return false; }
                            machine::text("K7 observed submitted Job output cancel\\n");
''' + anchor)
    anchor = '        if operation == abi::SYS_STATS {'
    change('kernel/dispatch_call.vt', anchor, anchor + '''
            if args[0_usize] == 100_usize { return answer(id, abi::OK, fs::test_stage()); }
            if args[0_usize] == 101_usize || args[0_usize] == 102_usize {
                let seen: usize = fs::test_seen();
                if !fs::test_arm(args[0_usize] - 100_usize) { return false; }
                return answer(id, abi::OK, seen);
            }
            if args[0_usize] == 103_usize { return answer(id, abi::OK, fs::test_seen()); }
''')


def programs(case):
    sources = ['abi/contract.vt', 'abi/syscalls.vt', 'abi/files.vt', 'abi/argument_wire.vt',
               'user/libsuba/syscall.vt', 'user/libsuba/arguments.vt', 'user/libsuba/argument_builder.vt',
               'user/libsuba/services.vt', 'user/libsuba/files.vt',
               'tests/k7/kernel_common.vt', 'tests/k7/kernel_cases.vt', 'tests/k7/kernel_cancel.vt', 'tests/k7/kernel_remount.vt']
    return [dict(entry='test::k7_kernel::' + name, sources=sources,
                 assembly=['user/libsuba/syscall.s0']) for name in [case + '_gate', 'worker']]


def run(out, command):
    command = [item for item in command if item != '-nographic']
    command += ['-display', 'none', '-serial', 'file:' + str(out / 'serial.log'), '-monitor', 'none',
                '-qmp', 'unix:' + str(out / 'qmp.sock') + ',server=on,wait=off']
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    start = time.monotonic()
    qmp = None
    record = {'passed': False, 'command': command}
    try:
        while time.monotonic() - start < 30 and not (out / 'qmp.sock').exists():
            require(process.poll() is None, 'QEMU exited before QMP')
            time.sleep(.05)
        qmp = Qmp(out / 'qmp.sock')
        while time.monotonic() - start < 180:
            require(process.poll() is None, 'QEMU exited before result')
            log = (out / 'serial.log').read_text() if (out / 'serial.log').exists() else ''
            require('panic' not in log.lower(), log[-2000:])
            qmp.call('screendump', {'filename': str(out / 'frame.ppm')})
            frame = Image.open(out / 'frame.ppm')
            frame.save(out / 'frame.png')
            pixel = frame.getpixel((0, 0))
            record['last_pixel'] = pixel
            record['collect_diagnostics'] = [frame.getpixel((i, 0)) for i in range(1, 5)]
            require(pixel[0] != 255, f'guest boundary fixture failed: {pixel[2]}, collect={record["collect_diagnostics"]}')
            if pixel == (0, 255, 0):
                record['passed'] = True
                return record
            time.sleep(.1)
        raise AssertionError('guest boundary fixture timed out')
    except Exception as error:
        record['error'] = str(error)
        raise
    finally:
        record['elapsed'] = time.monotonic() - start
        if qmp:
            (out / 'qmp.json').write_text(json.dumps(qmp.log, indent=2) + '\n')
        process.terminate()
        _, error = process.communicate(timeout=5)
        (out / 'stderr.log').write_bytes(error)
        (out / 'run.json').write_text(json.dumps(record, indent=2) + '\n')


def reboot_checks(out, command, record):
    """Boot copies twice; prove cleanup preserves every published byte and ledger."""
    import hashlib
    import shutil
    from read_disk import Disk
    contract = ROOT / 'abi/contract.vt'
    baseline = Path(record['disk_from']) if record['case'] == 'recovered' else out / 'disk.raw'
    before = Disk(baseline, contract)
    flags = [node['flags'] for node in before.nodes.values() if node['flags']]
    if record['case'] == 'remount':
        require(sorted(flags) == [1, 2, 3], 'all three synced lifecycle states required')
    expected_nodes = sum(node['flags'] == 0 for node in before.nodes.values())
    expected_blocks = sum((node['size'] + 4095) // 4096 for node in before.nodes.values()
                          if node['flags'] == 0 and node['kind'] == 1)
    expected = {path: hashlib.sha256(before.read(path)).hexdigest()
                for path, index in before.paths.items()
                if before.nodes[index]['kind'] == 1 and before.nodes[index]['flags'] == 0}
    record['durable_lifecycle'] = {'flags': flags, 'published_sha256': expected, 'boots': []}
    previous = out / 'disk.raw'
    for index in (1, 2):
        target = out / ('reboot' + str(index))
        target.mkdir()
        shutil.copyfile(previous, target / 'disk.raw')
        copied = sha(target / 'disk.raw')
        boot = [item.replace('file=' + str(out / 'disk.raw') + ',',
                             'file=' + str(target / 'disk.raw') + ',') for item in command]
        result = run(target, boot)
        after = Disk(target / 'disk.raw', contract)
        require(all(node['flags'] == 0 for node in after.nodes.values()), 'lifecycle nodes not reclaimed')
        actual = {path: hashlib.sha256(after.read(path)).hexdigest()
                  for path, node_index in after.paths.items() if after.nodes[node_index]['kind'] == 1}
        require(actual == expected, 'published bytes changed across reclamation')
        fat = struct.unpack_from('<65536I', after.data, 4096)
        blocks = sum(value != 0 for value in fat[193:48896])
        require(len(after.nodes) == expected_nodes and blocks == expected_blocks, 'reclaimed allocation ledger')
        (target / 'metadata.bin').write_bytes(after.data[:790528])
        record['durable_lifecycle']['boots'].append(dict(result=result, input_sha256=copied,
            output_sha256=sha(target / 'disk.raw'), nodes=len(after.nodes), allocated_blocks=blocks))
        previous = target / 'disk.raw'


def block_notifications(compiler, out):
    """Small production driver boundary probe; RAM MMIO is explicitly synthetic."""
    import shutil
    out.mkdir()
    files = ['kernel/device/io.vt', 'kernel/device/io.s0', 'kernel/device/virtio.vt',
             'kernel/device/block.vt', 'kernel/machine.vt', 'kernel/machine.s0',
             'tests/k4/transport/shutdown.s0', 'tests/k7/kernel_block.vt']
    record = dict(passed=False, compiler_sha256=sha(compiler), baseline='49b2213', cases=[],
        scope='real Read/PLIC completion; explicit callback replay and used/status corruption; '
              'RAM MMIO cases test state transitions and original deadline without hardware claims')
    try:
        pairs = [(True, mode) for mode in (0, 4, 5)] + [(False, mode) for mode in range(6)]
        for old, mode in pairs:
            case = out / (('old-' if old else 'new-') + str(mode))
            case.mkdir()
            for name in files:
                target = case / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if old and name in ('kernel/device/block.vt', 'kernel/device/virtio.vt'):
                    target.write_bytes(subprocess.check_output(['git', 'show', '49b2213:' + name], cwd=ROOT))
                else:
                    shutil.copyfile(ROOT / name, target)
            (case / 'config.vt').write_text('module test::config;\npub const MODE: usize = ' + str(mode) + ';\n')
            lines = ['format 1', 'profile suba-kernel', 'entry test::block::start',
                     'bind panic=test::block::panic', 'bind trap_dispatch=test::block::trap']
            lines += ['source ' + name for name in files if name.endswith('.vt')] + ['source config.vt']
            lines += ['assembly ' + name for name in files if name.endswith('.s0')] + ['output probe.elf']
            (case / 'probe.build').write_text('\n'.join(lines) + '\n')
            compile_command = ['qemu-riscv64', '-s', '1048576', str(compiler), 'build', 'probe.build']
            built = subprocess.run(compile_command, cwd=case, capture_output=True, timeout=120)
            (case / 'compile.log').write_bytes(built.stdout + built.stderr)
            require(built.returncode == 0, 'block probe compile failed: ' + str(case))
            with (case / 'disk.raw').open('xb') as disk:
                disk.truncate(268435456)
            command = ['qemu-system-riscv64', '-machine', 'virt', '-m', '512M', '-smp', '1',
                '-nographic', '-bios', str(FIRMWARE), '-kernel', str(case / 'probe.elf'), '-no-reboot',
                '-global', 'virtio-mmio.force-legacy=false', '-drive',
                f'file={case}/disk.raw,if=none,format=raw,id=blk', '-device', 'virtio-blk-device,drive=blk']
            try:
                ran = subprocess.run(command, capture_output=True, timeout=5)
                log, code = ran.stdout + ran.stderr, ran.returncode
            except subprocess.TimeoutExpired as error:
                log, code = (error.stdout or b'') + (error.stderr or b''), None
            (case / 'boot.log').write_bytes(log)
            expected = {0: b'FAIL 0a', 4: b'FAIL 18', 5: b'FAIL 1f'}
            passed = expected[mode] in log if old else code == 0 and b'PASS' in log and b'FAIL' not in log
            record['cases'].append(dict(old=old, mode=mode, passed=passed, exit=code, command=command,
                compile_command=compile_command, elf_sha256=sha(case / 'probe.elf'),
                inputs={name: sha(case / name) for name in files}))
            require(passed, 'block probe result: ' + str(case))
        record['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')


def block_failures(compiler, out, kernel_from, disk_from):
    """Real backend delay/EIO, no production source mutation or timeout change."""
    import re
    import shutil
    require(kernel_from is not None and disk_from is not None, 'block_failure needs --kernel-from and --disk-from')
    source = json.loads((kernel_from / 'verification.json').read_text())
    require(source['passed'] and source['compiler_sha256'] == sha(compiler), 'verified matching kernel required')
    require(source['kernel']['sha256'] == sha(kernel_from / 'build/kernel.elf'), 'kernel ELF hash changed')
    out.mkdir()
    command = json.loads((kernel_from / 'run.json').read_text())['command']
    command = command[:command.index('-display')]
    record = dict(passed=False, kernel_from=str(kernel_from), kernel_sha256=source['kernel']['sha256'],
                  disk_from=str(disk_from), disk_from_sha256=sha(disk_from), cases=[],
                  scope='blkdebug positive controls for final mount FLUSH diagnostics; not historical panic attribution')
    try:
        for name, delay, errno in [('within-deadline', 500000000, 0), ('past-deadline', 1200000000, 0), ('device-eio', 0, 5)]:
            target = out / name
            target.mkdir()
            shutil.copyfile(disk_from, target / 'disk.raw')
            (target / 'blkdebug.conf').write_text('[inject-error]\nevent = "flush_to_disk"\niotype = "flush"\n'
                f'errno = "{errno}"\ndelay-ns = "{delay}"\nonce = "on"\n')
            cmd = command.copy()
            cmd[cmd.index('-drive') + 1] = (f'file=blkdebug:{target}/blkdebug.conf:{target}/disk.raw,'
                'if=none,format=raw,id=blk,cache=writeback,rerror=report,werror=report')
            (target / 'events.txt').write_text('virtio_blk_req_complete\nvirtio_mmio_setting_irq\n')
            cmd += ['-trace', f'events={target}/events.txt,file={target}/trace.log']
            result = None
            try:
                result = run(target, cmd)
            except ValueError:
                # Failure is acceptable only with the complete exact tuple below.
                pass
            log = (target / 'serial.log').read_text()
            lines = [line for line in log.splitlines() if line.startswith(('storage failure ', 'block failure '))]
            fields = {key: value for line in lines for key, value in re.findall(r'(\w+)=([\w.]+)', line)}
            if name == 'within-deadline':
                passed = result is not None and result['passed'] and not lines
            else:
                # phase is the last entered FS step. A fast EIO can arrive
                # immediately after step8 submits Flush, before step9 is entered.
                expected_path = 'mount.fs' if name == 'past-deadline' else 'mount.hub'
                passed = ('panic reason=70' in log and len(lines) == 2 and fields['path'] == expected_path
                    and fields['phase'] in (('9',) if name == 'past-deadline' else ('8', '9'))
                    and fields['command'] == '4' and fields['state'] == 'submitted'
                    and fields['reason'] == ('7' if name == 'past-deadline' else '6'))
                if name == 'past-deadline':
                    passed &= (int(fields['observed']) - int(fields['began']) > 10000000
                        and fields['used'] == fields['consumed'] and fields['irq'] == '0' and fields['status'] == '255')
                else:
                    passed &= int(fields['used']) == int(fields['consumed']) + 1 and fields['status'] == '1'
            record['cases'].append(dict(name=name, delay_ns=delay, errno=errno, passed=passed,
                diagnostics=lines, fields=fields, elapsed=json.loads((target / 'run.json').read_text())['elapsed']))
            require(passed, 'block failure classification: ' + str(target))
        require(sha(disk_from) == record['disk_from_sha256'], 'source disk changed')
        record['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--case', choices=['images', 'job', 'publication', 'death', 'load_cancel', 'job_dma', 'job_owner', 'remount', 'recovered', 'historical', 'block_notification', 'block_failure'], default='images')
    parser.add_argument('--kernel-from', type=Path)
    parser.add_argument('--without-user-irq', action='store_true')
    parser.add_argument('--disk-from', type=Path, help='Copy an existing stopped disk; never modify its source')
    args = parser.parse_args()
    out, compiler = args.out.resolve(), args.compiler.resolve()
    if args.case == 'block_notification':
        block_notifications(compiler, out)
        return
    if args.case == 'block_failure':
        block_failures(compiler, out, args.kernel_from.resolve() if args.kernel_from else None,
                       args.disk_from.resolve() if args.disk_from else None)
        return
    record = {'passed': False, 'case': args.case, 'compiler_sha256': sha(compiler),
              'firmware_sha256': sha(FIRMWARE), 'source_inputs': kernel_probe.snapshot(out)}
    if args.case in ('load_cancel', 'job_dma'):
        observe_cancel(out, args.without_user_irq)
        record['observer'] = 'real submitted DMA held until U cancellation; U external IRQ required'
        record['without_user_irq'] = args.without_user_irq
    try:
        command = kernel_probe.build(compiler, out, programs(args.case), record,
                                     args.kernel_from.resolve() if args.kernel_from else None)
        tree = out / 'initial'
        for directory in ['sys', 'work', 'jobs']:
            (tree / directory).mkdir(parents=True)
        worker = (out / 'build/user1.elf').read_bytes()
        (tree / 'sys/worker').write_bytes(worker)
        (tree / 'work/worker').write_bytes(worker)
        (tree / 'work/target').write_bytes(b'old')
        (tree / 'sys/bad').write_bytes(b'not an ELF')
        rwx = bytearray(worker)
        table = struct.unpack_from('<Q', rwx, 32)[0]
        struct.pack_into('<I', rwx, table + 4, 7)
        (tree / 'sys/rwx').write_bytes(rwx)
        if args.disk_from:
            import shutil
            original = args.disk_from.resolve()
            record['disk_from'] = str(original)
            record['disk_from_sha256'] = sha(original)
            shutil.copyfile(original, out / 'disk.raw')
        else:
            record['initial_disk'] = format_disk(tree, out / 'disk.raw', out / 'abi/contract.vt')
        command += ['-global', 'virtio-mmio.force-legacy=false', '-device', 'virtio-keyboard-device',
                    '-device', 'virtio-tablet-device', '-drive',
                    f'file={out}/disk.raw,if=none,format=raw,id=blk,cache=writeback',
                    '-device', 'virtio-blk-device,drive=blk']
        record['result'] = run(out, command)
        if args.case in ('remount', 'recovered', 'historical'):
            reboot_checks(out, command, record)
        if args.case in ('load_cancel', 'job_dma'):
            log = (out / 'serial.log').read_text()
            marker = 'K7 observed submitted FS load cancel' if args.case == 'load_cancel' else 'K7 observed submitted Job output cancel'
            require(log.count(marker) == 100, 'all 100 real submitted cancellation windows required')
            record['cancel_rounds'] = 100
        record['passed'] = True
    except Exception as error:
        record['error'] = str(error)
        raise
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    print('K7 protected kernel probe passed:', args.case)


if __name__ == '__main__':
    main()
