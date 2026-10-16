#!/usr/bin/env python3
"""Measure the real desktop under two concurrent native compiler workloads.

Snapshot-only timing observers; no 304-field lifecycle scanning. Targets are
reported as measurements, never used to turn a functional failure into success.
"""
import argparse
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import time
from PIL import Image
import build_users
import kernel_probe
import native_probe
from build_system import manifest_program
from check_k2 import sha
from check_k5_devices import Qmp
from mkfs import format_disk
from read_disk import Disk

ROOT = Path(__file__).resolve().parents[1]


def replace(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, (path, old)
    path.write_text(text.replace(old, new))


def instrumentation(out):
    # First timestamp follows saving t0, before the remaining trap save/CSR work.
    replace(out / 'kernel/trap.s0', 'sd x5, 32(x2)',
            'sd x5, 32(x2)\ncsrrs x5, 3073, x0\nsd x5, 280(x2)')
    entry = out / 'kernel/entry.vt'
    replace(entry, '        machine::activate(space::kernel_token());\n        match process::capture(frame)',
            '        dispatch::perf_begin(*core::ptr::<usize>(frame + 280_usize));\n        machine::activate(space::kernel_token());\n        match process::capture(frame)')
    replace(entry, '        return schedule();',
            '        let selected: usize = schedule();\n        dispatch::perf_end();\n        return selected;')
    replace(entry, '                if !dispatch::step()', '                dispatch::perf_pages();\n                if !dispatch::step()')
    # WFI is not continuous CPU work. End a segment before idle, resume afterwards.
    replace(entry, '                        machine::idle();',
            '                        dispatch::perf_end(); machine::idle(); dispatch::perf_begin(machine::time());')
    owner = out / 'kernel/dispatch.vt'
    owner.write_text(owner.read_text() + '\n' + (ROOT / 'tests/k10/performance_kernel.vt').read_text().replace('module kernel::dispatch;', ''))
    call = out / 'kernel/dispatch_call.vt'
    extra = '''
            if args[0_usize] >= 210_usize && args[0_usize] <= 219_usize {
                if args[0_usize] != 215_usize && !process::trusted_desktop(id) { return answer(id, abi::DENIED, 0); }
                if args[0_usize] == 210_usize { perf_reset(); }
                if args[0_usize] == 216_usize { machine::text("PERF WINDOWS\\n"); }
                if args[0_usize] == 211_usize {
                    if !perf_bind(id, args[1_usize], 0) || !perf_bind(id, args[2_usize], 1) { return answer(id, abi::INVALID, 0); }
                    machine::text("PERF CHILDREN "); number(process::slot(PERF_CHILD[0_usize])); machine::text(" ");
                    number(process::generation(PERF_CHILD[0_usize])); machine::text(" ");
                    number(process::slot(PERF_CHILD[1_usize])); machine::text(" "); number(process::generation(PERF_CHILD[1_usize]));
                    perf_states(); machine::text("\\nPERF READY\\n");
                }
                if args[0_usize] == 212_usize {
                    let delay: usize = machine::time() - args[2_usize];
                    machine::text("PERF INPUT "); number(args[1_usize]); machine::text(" delay ");
                    number(delay); perf_states(); machine::text("\\n");
                }
                if args[0_usize] == 213_usize {
                    machine::text("PERF FRAME "); number(args[1_usize]); machine::text(" bytes "); number(args[2_usize]);
                    machine::text(" measuring "); if PERF_ACTIVE { number(1); } else { number(0); } machine::text("\\n");
                }
                if args[0_usize] == 215_usize {
                    let delay: usize = machine::time() - args[2_usize];
                    machine::text("PERF APP "); number(args[1_usize]); machine::text(" delay ");
                    number(delay); perf_states(); machine::text("\\n");
                }
                if args[0_usize] == 217_usize {
                    machine::text("PERF RESOURCE "); number(args[1_usize]); machine::text(" selector "); number(args[2_usize]);
                    machine::text(" status "); number(args[3_usize]); machine::text(" value "); number(args[4_usize]); machine::text("\\n");
                }
                if args[0_usize] == 218_usize { perf_pages(); perf_end(); PERF_ACTIVE = false; }
                if args[0_usize] == 219_usize {
                    machine::text("PERF COLLECT "); number(args[1_usize]); machine::text(" status "); number(args[2_usize]);
                    machine::text(" cause "); number(args[3_usize]); machine::text(" ticks "); number(machine::time()); machine::text("\\n");
                }
                if args[0_usize] == 214_usize { perf_report(); machine::text("PERF DONE\\n"); }
                return answer(id, abi::OK, 0);
            }
'''
    # Qualified modules still require an import in S-next.
    replace(call, '        if operation == abi::SYS_STATS {', '        if operation == abi::SYS_STATS {' + extra)
    replace(out / 'kernel/device/input.vt', 'a: a, b: b, c: c, d: 0 };', 'a: a, b: b, c: c, d: io::time() };')
    app = out / 'user/edit/app.vt'
    replace(app, 'static mut RUN_CHILD: usize = 0;', 'static mut RUN_CHILD: usize = 0;\nstatic mut COST_INPUT_COUNT: usize = 0;')
    replace(app, '                            act(core::addr_of_mut(document), key_event(event.a, event.b));',
        '                            if event.a == 64_usize && event.b == 1_usize {\n                                COST_INPUT_COUNT = COST_INPUT_COUNT + 1_usize;\n                                let measured: syscall::Reply = syscall::invoke(abi::SYS_STATS, 215, COST_INPUT_COUNT, event.d, 0, 0, 0);\n                            }\n                            act(core::addr_of_mut(document), key_event(event.a, event.b));')
    desktop = out / 'user/desktop/main.vt' 
    text = desktop.read_text()
    text = text.replace('module user::desktop;', 'module user::desktop;\nimport libsuba::files as cost_fs;\nimport suba::files as cost_files;')
    text += (ROOT / 'tests/k10/performance_desktop.vt').read_text().replace('module user::desktop::main;', '')
    desktop.write_text(text)
    replace(desktop, '            collect_editors();', '            collect_editors();\n            if COST_STARTED && !cost_poll() { return fail(8); }')
    replace(desktop, '                if !render() {', '                let render_start: syscall::Reply = services::stats(syscalls::STATS_TIME_TICKS);\n                let render_bytes: usize = DAMAGE.width * DAMAGE.height * 4_usize;\n                if !render() {')
    replace(desktop, '                deadline = after.value + FRAME_TICKS;', '''                deadline = after.value + FRAME_TICKS;
                let measured: syscall::Reply = syscall::invoke(abi::SYS_STATS, 213, after.value - render_start.value, render_bytes, 0, 0, 0);
                if !COST_WINDOWS && LIST.count == 2_usize && LIST.items[0_usize].damage > 1_usize &&
                    LIST.items[1_usize].damage > 1_usize {
                    COST_WINDOWS = true;
                    let ready: syscall::Reply = syscall::invoke(abi::SYS_STATS, 216, 0, 0, 0, 0, 0);
                }
                if !COST_STARTED && COST_WINDOWS && focused() != windows::WINDOW_CAPACITY {
                    if !cost_start() { return fail(9); }
                }''')
    replace(desktop, '        var control: usize = 0;', '''        if event.a == 64_usize && event.b == 1_usize {
            COST_INPUTS = COST_INPUTS + 1_usize;
            let measured: syscall::Reply = syscall::invoke(abi::SYS_STATS, 212, COST_INPUTS, event.d, 2_usize - COST_DONE, 0, 0);
        }
        var control: usize = 0;''')
    replace(desktop, '            var watches: [3]services::Watch = zero;', '            var watches: [7]services::Watch = zero;')
    replace(desktop, '            let active: []const services::Watch', '''            i = 0;
            while i < 2_usize {
                if COST_PIPE[i] != 0_usize {
                    watches[watched] = make services::Watch { handle: COST_PIPE[i], events: syscalls::READABLE };
                    watched = watched + 1_usize;
                }
                if COST_CHILD[i] != 0_usize {
                    watches[watched] = make services::Watch { handle: COST_CHILD[i], events: syscalls::EXITED };
                    watched = watched + 1_usize;
                }
                i = i + 1_usize;
            }
            let active: []const services::Watch''')


def run(out, command, seconds):
    command = [item for item in command if item != '-nographic'] + [
        '-display', 'none', '-serial', 'file:' + str(out / 'serial.log'), '-monitor', 'none',
        '-qmp', 'unix:' + str(out / 'qmp.sock') + ',server=on,wait=off']
    start = time.monotonic()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    result = {'passed': False, 'command': command, 'samples': []}
    qmp = None
    try:
        def log():
            assert process.poll() is None, 'QEMU exited before completion'
            path = out / 'serial.log'
            value = path.read_text() if path.exists() else ''
            assert 'panic' not in value.lower() and 'root exit' not in value.lower(), value[-4000:]
            assert time.monotonic() - start < seconds, 'performance deadline'
            return value
        while not (out / 'qmp.sock').exists():
            log(); time.sleep(.05)
        qmp = Qmp(out / 'qmp.sock')
        while 'PERF WINDOWS' not in log():
            time.sleep(.05)
        qmp.input([{'type': 'abs', 'data': {'axis': 'x', 'value': 50 * 32767 // 1024}},
                   {'type': 'abs', 'data': {'axis': 'y', 'value': 150 * 32767 // 768}}])
        for down in (True, False):
            qmp.input([{'type': 'btn', 'data': {'down': down, 'button': 'left'}}])
        while 'PERF READY' not in log():
            time.sleep(.05)
        for index in range(1, 101):
            before = time.monotonic()
            # No fixed 100ms sleep from Qmp.input: it would bias the target itself.
            qmp.call('input-send-event', {'events': [
                {'type': 'key', 'data': {'down': down, 'key': {'type': 'qcode', 'data': 'f6'}}}
                for down in (True, False)]})
            while not re.search(rf'PERF APP {index} delay (\d+) states (\d+) (\d+)\n', log()):
                assert time.monotonic() - before < 90, 'input not delivered to application within 90s; do not discard sample'
                time.sleep(.005)
            match = re.search(rf'PERF INPUT {index} delay (\d+) states (\d+) (\d+)\n', log())
            application = re.search(rf'PERF APP {index} delay (\d+) states (\d+) (\d+)\n', log())
            assert match and application, 'complete desktop/application pair required'
            result['samples'].append({'index': index, 'driver_to_desktop_ms': int(match[1]) / 10000,
                                      'driver_to_app_ms': int(application[1]) / 10000,
                                      'desktop_compiler_states': [int(match[2]), int(match[3])],
                                      'app_compiler_states': [int(application[2]), int(application[3])],
                                      'host_injection_to_serial_ms': (time.monotonic() - before) * 1000})
            if index % 20 == 0:
                print(json.dumps({'input_samples': index, 'elapsed': time.monotonic() - start}), flush=True)
        while 'PERF DONE' not in log():
            time.sleep(.1)
        serial = log()
        qmp.call('screendump', {'filename': str(out / 'frame.ppm')})
        Image.open(out / 'frame.ppm').save(out / 'frame.png')
        s = re.search(r'PERF S (\d+) samples (\d+) baseline (\d+) pages (\d+) peak (\d+) slice (\d+)', serial)
        assert s
        result['supervisor'] = dict(max_segment_ms=int(s[1]) / 10000, segments=int(s[2]),
                                    baseline_allocated_pages=int(s[3]), final_allocated_pages=int(s[4]),
                                    final_minus_baseline_pages=int(s[4]) - int(s[3]),
                                    peak_sampled_allocated_pages=int(s[5]),
                                    peak_minus_baseline_pages=int(s[5]) - int(s[3]),
                                    dispatch_only_max_ms=int(s[6]) / 10000)
        result['frames'] = [{'ms': int(a) / 10000, 'present_bytes': int(b), 'during_measurement': c == '1'}
                            for a, b, c in re.findall(r'PERF FRAME (\d+) bytes (\d+) measuring (\d+)', serial)]
        identities = re.search(r'PERF CHILDREN (\d+) (\d+) (\d+) (\d+) states (\d+) (\d+)', serial)
        assert identities, 'actual process identities required'
        result['native_compiler_identities'] = [dict(slot=int(identities[1]), generation=int(identities[2])),
                                                dict(slot=int(identities[3]), generation=int(identities[4]))]
        assert result['native_compiler_identities'][0] != result['native_compiler_identities'][1]
        active = [v for v in result['samples'] if all(state in (2, 3, 4)
                  for state in v['desktop_compiler_states'] + v['app_compiler_states'])]
        assert len(active) == 100, 'all 100 desktop and app samples must observe both real compiler identities Ready/Running/Blocked'
        for field in ('driver_to_desktop_ms', 'driver_to_app_ms', 'host_injection_to_serial_ms'):
            values = sorted(v[field] for v in active)
            result[field] = {'p50': values[49], 'p99': values[98], 'max': values[-1]}
        result['resources'] = [dict(checkpoint=int(checkpoint), selector=int(selector), status=int(status), value=int(value))
            for checkpoint, selector, status, value in re.findall(r'PERF RESOURCE (\d+) selector (\d+) status (\d+) value (\d+)', serial)]
        checkpoints = {}
        for item in result['resources']:
            checkpoints.setdefault(item['checkpoint'], {})[item['selector']] = dict(status=item['status'], value=item['value'])
        expected_selectors = {0, 3, 8, 9}
        assert checkpoints and all(set(sample) == expected_selectors and all(v['status'] == 0 for v in sample.values()) for sample in checkpoints.values())
        startup = sorted(k for k in checkpoints if k < 100)
        final = sorted(k for k in checkpoints if k >= 100)
        assert len(startup) >= 4 and len(final) >= 3, 'three stable confirmations needed at both ends'
        baseline = checkpoints[startup[-1]]
        assert all(checkpoints[k] == baseline for k in startup[-3:] + final[-3:]), 'four resource classes must return to stable pre-compiler baseline'
        result['stable_resource_baseline'] = baseline
        result['stable_resource_final'] = checkpoints[final[-1]]
        collected = re.findall(r'PERF COLLECT (\d+) status (\d+) cause (\d+) ticks (\d+)', serial)
        assert sorted((int(i), int(status), int(cause)) for i, status, cause, ticks in collected) == [(0, 0, 0), (1, 0, 0)]
        result['collected'] = [dict(index=int(i), status=int(status), cause=int(cause), ticks=int(ticks)) for i, status, cause, ticks in collected]
        result['targets'] = {'input_p99_100ms_met': result['driver_to_desktop_ms']['p99'] <= 100,
                             's_segment_5ms_met': result['supervisor']['max_segment_ms'] <= 5}
        result['passed'] = True
        return result
    except BaseException as error:
        result['failure'] = repr(error)
        raise
    finally:
        result['elapsed'] = time.monotonic() - start
        process.terminate(); _, error = process.communicate(timeout=10)
        (out / 'stderr.log').write_bytes(error)
        if qmp:
            (out / 'qmp.json').write_text(json.dumps(qmp.log, indent=2) + '\n')
        (out / 'run.json').write_text(json.dumps(result, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--kernel-from', type=Path)
    parser.add_argument('--seconds', type=int, default=2400)
    args = parser.parse_args()
    out, system, compiler = args.out.resolve(), args.system.resolve(), args.compiler.resolve()
    record = {'passed': False, 'stage_acceptance': False, 'scope': 'K10 performance exploration',
              'compiler_sha256': sha(compiler), 'source_inputs': kernel_probe.snapshot(out),
              'measurement_boundaries': {
                  's_segment': 'rdtime after saving t0 to schedule return; WFI splits active segments; final restore/sret tail and early trap prefix excluded',
                  'input': 'virtio enqueue timestamp to desktop or editor stats entry; excludes device-before-enqueue latency; host QMP-to-serial is a separate diagnostic',
                  'observer_cost': 'timing reads, two checked process identity reads, per-input/frame UART; included in runtime and may increase measured latency',
                  'memory': 'allocator allocated pages only, excludes boot-reserved/static kernel/ramfb; baseline after focused redraw and three stable confirmations before compiler spawn; sampled peak before dispatch; timing stops after both collect/log close/sync, final counters require three baseline-equal confirmations outside timing',
                  'limits': 'no 304-field ledger; no exact transient allocation peak or claim of complete resource recovery; no production latency acceptance'}}
    record['tool_inputs'] = {}
    for name in ['tools/check_k10_performance.py', 'tests/k10/performance_kernel.vt', 'tests/k10/performance_desktop.vt',
                 'tools/kernel_probe.py', 'tools/native_probe.py', 'tools/build_users.py', 'tools/build_system.py',
                 'tools/check_k2.py', 'tools/check_kernel_entry.py', 'tools/check_k5_devices.py', 'tools/mkfs.py', 'tools/read_disk.py']:
        target = out / 'tool_snapshot' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
        record['tool_inputs'][name] = sha(target)
    try:
        program = manifest_program(ROOT / 'user/desktop/desktop.build')
        program['sources'] += ['abi/files.vt', 'user/libsuba/files.vt']
        editor = manifest_program(ROOT / 'user/edit/edit.build')
        for name in program['sources'] + program['assembly'] + editor['sources'] + editor['assembly']:
            target = out / name
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(build_users.source_path(name), target)
        record['desktop_inputs'] = {name: sha(out / name) for name in program['sources'] + program['assembly']}
        instrumentation(out)
        command = kernel_probe.build(compiler, out, [program, editor], record, args.kernel_from.resolve() if args.kernel_from else None)
        tree = out / 'initial'
        shutil.copytree(system / 'initial', tree)
        shutil.copyfile(out / 'build/user1.elf', tree / 'sys/edit.elf')
        names = build_users.compiler_sources()
        base = ['format 1', 'profile suba-user', 'entry bootstrap::main::run']
        base += ['source system/' + name for name in names] + ['assembly system/user/libsuba/syscall.s0']
        previous = json.loads((system / 'verification.json').read_text())
        for name in names + ['user/libsuba/syscall.s0']:
            assert sha(tree / 'work/system' / name) == previous['programs']['compiler']['inputs'][name]
        for i in range(2):
            (tree / f'work/cost{i}.build').write_text('\n'.join(base + [f'output cost{i}.elf']) + '\n')
        record['initial_compiler_sha256'] = sha(tree / 'sys/compiler.elf')
        record['system_source'] = str(system)
        record['system_verification_sha256'] = sha(system / 'verification.json')
        record['initial_disk'] = format_disk(tree, out / 'disk.raw', out / 'abi/contract.vt')
        record['measurement'] = run(out, native_probe.devices(command, out / 'disk.raw'), args.seconds)
        disk = Disk(out / 'disk.raw', out / 'abi/contract.vt')
        record['native_outputs'] = []
        for i in range(2):
            data = disk.read(f'/work/cost{i}.elf')
            assert data == (tree / 'sys/compiler.elf').read_bytes()
            (out / f'cost{i}.log').write_bytes(disk.read(f'/work/cost{i}.log'))
            import hashlib
            record['native_outputs'].append(dict(path=f'/work/cost{i}.elf', bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                                                equals_initial_compiler=True, log=f'cost{i}.log'))
        record['native_fixed_point_equal'] = True
        record['passed'] = True
    except BaseException as error:
        record['failure'] = repr(error)
        raise
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    print('K10 cost measurement completed; target attainment is reported separately')


if __name__ == '__main__':
    main()
