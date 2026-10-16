#!/usr/bin/env python3
"""K10 preparatory FS-loader migration, not formal stage acceptance.

All ordinary workers are stored on the initial disk. Only the trusted U test
controller is started from RAM; the common builder also reserves an unused RAM
copy of the worker. Optional source-kernel-from pins exploration to a
validated historical snapshot; current production files are never edited.
"""
import argparse
import json
from pathlib import Path
import shutil
import kernel_probe
from check_k2 import sha
from check_k7_kernel import run, observe_cancel
from check_k5_lifecycle import run as window_run
from check_k5_lifecycle import observe as observe_races
from check_kernel_entry import FIRMWARE, require
from mkfs import format_disk

ROOT = Path(__file__).resolve().parents[1]
COMMON = ['abi/contract.vt', 'abi/windows.vt', 'abi/syscalls.vt', 'abi/files.vt',
          'abi/argument_wire.vt', 'user/libsuba/argument_builder.vt',
          'user/libsuba/arguments.vt', 'user/libsuba/syscall.vt',
          'user/libsuba/services.vt', 'user/libsuba/windows.vt']


def snapshot(out, source):
    if source is None:
        return kernel_probe.snapshot(out)
    previous = json.loads((source / 'verification.json').read_text())
    require(previous['kernel']['sha256'] == sha(source / 'build/kernel.elf'), 'historical kernel identity')
    names = ['kernel/kernel.build', 'tests/k0/boot.vt', 'tests/k0/fw_cfg.vt']
    names += [line.split(' ', 1)[1] for line in (source / 'kernel/kernel.build').read_text().splitlines()
              if line.startswith(('source ', 'assembly '))]
    out.mkdir(parents=True, exist_ok=False)
    (out / 'build').mkdir()
    inputs = {}
    for name in names:
        expected = previous.get('compiled_inputs', {}).get(name) or previous['source_inputs'][name]
        require(sha(source / name) == expected, 'historical source identity: ' + name)
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
        inputs[name] = expected
    return inputs


def observe(out):
    owners = {'objects': 'kernel/objects.vt', 'request': 'kernel/request.vt',
              'process': 'kernel/process.vt', 'space': 'kernel/space.vt',
              'window': 'kernel/window.vt', 'ranges': 'kernel/ranges.vt',
              'image_reads': 'kernel/image_reads.vt', 'fs': 'kernel/fs/state.vt',
              'block': 'kernel/device/block.vt'}
    for owner, destination in owners.items():
        template = out / f'tests/k10/observers/{owner}.vt'
        template.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / f'tests/k10/observers/{owner}.vt', template)
        target = out / destination
        target.write_text(target.read_text() + '\n' + template.read_text())
    path = out / 'kernel/dispatch_call.vt'
    source = path.read_text()
    anchor = '        if operation == abi::SYS_STATS {'
    require(source.count(anchor) == 1, 'stats observer anchor')
    source = source.replace(anchor, anchor + '''
            if args[0_usize] == 200_usize { return answer(id, abi::OK, k10_state(id, args[1_usize])); }
            if args[0_usize] == 201_usize {
                if !k10_ledger(id, args[1_usize], false) { return answer(id, abi::INVALID, 0); }
                k10_record(args[1_usize], args[2_usize]);
                return answer(id, abi::OK, 0);
            }
            if args[0_usize] == 202_usize {
                if !k10_ledger(id, 0, true) { return answer(id, abi::INVALID, 0); }
                return answer(id, abi::OK, 0);
            }
''')
    observer = out / 'tests/k10/observer.vt'
    observer.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / 'tests/k10/observer.vt', observer)
    path.write_text(source + '\n' + observer.read_text())


def observe_update(out):
    """Hold a real partially copied WindowUpdate until the ordinary U parent kills."""
    path = out / 'kernel/dispatch_window.vt'
    source = path.read_text()
    anchor = '        if !window::live(transfer.copy.window) { return finish(work, abi::BAD_HANDLE, 0); }'
    require(source.count(anchor) == 1, 'window update hold anchor')
    source = source.replace(anchor, anchor + '\n        if transfer.writing && transfer.done == 2048_usize { return true; }')
    anchor = '        next.done = next.done + part.bytes;'
    require(source.count(anchor) == 1, 'window update progress anchor')
    source = source.replace(anchor, anchor + '\n        if transfer.writing && next.done == 2048_usize { machine::text("K10 WindowUpdate first piece held\\n"); }')
    path.write_text(source)
    path = out / 'kernel/dispatch_call.vt'
    source = path.read_text()
    anchor = 'request::Operation::WindowCopy(value) => {}'
    require(source.count(anchor) == 1, 'window update state observer anchor')
    path.write_text(source.replace(anchor, 'request::Operation::WindowCopy(value) => { if value.writing && value.done == 2048_usize { return 3; } }'))


def programs(mode):
    if mode in ('windowupdate', 'windowlife', 'windowrace', 'queue'):
        sources = COMMON + ['tests/k10/window.vt', 'tests/k10/config.vt']
        entry = {'windowupdate': 'updating', 'windowlife': 'lifecycle', 'windowrace': 'copy_race', 'queue': 'queues'}[mode]
        names = ['test::k10_window::' + entry,
                 'test::k10_window::producer']
        assembly = ['user/libsuba/syscall.s0']
    elif mode in ('loading', 'dma'):
        sources = COMMON + ['user/libsuba/files.vt', 'tests/k10/dma.vt', 'tests/k10/config.vt']
        names = ['test::k10_dma::' + mode, 'test::k10_dma::worker']
        assembly = ['user/libsuba/syscall.s0']
    else:
        sources = COMMON + ['tests/k10/lifecycle.vt', 'tests/k10/config.vt', 'tests/k10/memory.vt',
                            'tests/k10/streams.vt', 'tests/k10/handles.vt']
        names = ['test::k10::' + mode, 'test::k10::worker']
        assembly = ['user/libsuba/syscall.s0', 'tests/k10/faults.s0']
    return [dict(entry=name, sources=sources, assembly=assembly) for name in names]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--mode', required=True, choices=['ready', 'streamwait', 'windowupdate', 'windowlife', 'windowrace', 'queue', 'identity', 'isolation', 'ledgercontrol', 'loading', 'dma'])
    parser.add_argument('--rounds', type=int, default=100, help='ordinary rounds; windowrace adds two interleavings')
    parser.add_argument('--race-observer', action='store_true', help='also compile the two window interleavings for kernel reuse with windowrace')
    parser.add_argument('--source-kernel-from', type=Path, help='validated frozen baseline sources for exploration')
    parser.add_argument('--kernel-from', type=Path, help='exact same observed kernel inputs to reuse')
    args = parser.parse_args()
    require(1 <= args.rounds <= 100, 'rounds must be 1..100')
    require(not args.race_observer or args.mode not in ('windowupdate', 'windowlife', 'queue'), 'race observer is incompatible with ordinary window expectations')
    out, compiler = args.out.resolve(), args.compiler.resolve()
    source = args.source_kernel_from.resolve() if args.source_kernel_from else None
    record = dict(passed=False, stage_acceptance=False, scope='K10 preparatory exploration', mode=args.mode,
                  compiler_sha256=sha(compiler), firmware_sha256=sha(FIRMWARE),
                  source_kernel_from=str(source) if source else None, source_inputs=snapshot(out, source),
                  ordinary_rounds=args.rounds,
                  ledger='owner-local counters/frame validation; controller slot excluded and separately reported; not performance evidence')
    record['tool_inputs'] = {name: sha(ROOT / name) for name in (
        'tools/check_k10_lifecycle.py', 'tools/kernel_probe.py', 'tools/check_k7_kernel.py',
        'tools/check_k5_lifecycle.py', 'tools/check_k5_devices.py', 'tools/check_k2.py',
        'tools/check_kernel_entry.py', 'tools/mkfs.py')}
    for name in record['tool_inputs']:
        target = out / 'tool_snapshot' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    try:
        observe(out)
        record['race_observer'] = args.race_observer or args.mode == 'windowrace'
        if record['race_observer']:
            observe_races(out)
        record['window_update_observer'] = args.mode == 'windowupdate'
        if record['window_update_observer']:
            observe_update(out)
        record['dma_observer'] = args.mode in ('loading', 'dma')
        if record['dma_observer']:
            require(not record['race_observer'], 'DMA and window scheduling observers are separate')
            observe_cancel(out)
            target = out / 'kernel/dispatch_call.vt'
            text = target.read_text()
            anchor = '        if operation == abi::SYS_STATS {'
            require(text.count(anchor) == 1, 'loading observer anchor')
            target.write_text(text.replace(anchor, anchor + '''
            if args[0_usize] == 203_usize {
                var count: usize = 0; var slot: usize = 0;
                while slot < 16_usize {
                    if process::k10_state(slot) == 1_usize { count = count + 1_usize; }
                    slot = slot + 1_usize;
                }
                return answer(id, abi::OK, count);
            }
'''))
        record['observer_sha256'] = sha(out / 'tests/k10/observer.vt')
        record['owner_observers'] = {str(path.relative_to(out)): sha(path) for path in (out / 'tests/k10/observers').glob('*.vt')}
        (out / 'tests/k10/config.vt').write_text('module test::k10_config;\npub const ROUNDS: usize = ' + str(args.rounds) + ';\n')
        command = kernel_probe.build(compiler, out, programs(args.mode), record,
                                     args.kernel_from.resolve() if args.kernel_from else None)
        tree = out / 'initial'
        for name in ('sys', 'work', 'jobs'):
            (tree / name).mkdir(parents=True)
        shutil.copyfile(out / 'build/user1.elf', tree / 'sys/worker')
        record['initial_disk'] = format_disk(tree, out / 'disk.raw', out / 'abi/contract.vt')
        command += ['-global', 'virtio-mmio.force-legacy=false', '-device', 'virtio-keyboard-device',
                    '-device', 'virtio-tablet-device', '-drive',
                    f'file={out}/disk.raw,if=none,format=raw,id=blk,cache=writeback', '-device', 'virtio-blk-device,drive=blk']
        # The boot helper reserves both fixture binaries, but dispatch boots only
        # controller index0. The second image is never an ordinary spawn provider.
        record['ordinary_worker'] = {'path': '/sys/worker', 'sha256': sha(tree / 'sys/worker')}
        if args.mode == 'queue':
            command += ['-display', 'none']
            record['result'] = window_run(out, command, 'queue')
            log = (out / 'queue/serial.log').read_text()
        else:
            record['result'] = run(out, command)
            log = (out / 'serial.log').read_text()
        rounds = []
        for line in log.splitlines():
            if line.startswith('K10 round '):
                words = line.split()
                rounds.append(dict(round=int(words[2]), state=int(words[4]), pages=int(words[6]),
                    streams=int(words[8]), children=int(words[10]), jobs=int(words[12]),
                    fs=dict(zip(['free_blocks', 'free_nodes', 'files', 'requests', 'block_state', 'detached'], map(int, words[13:])))))
        record['rounds'] = rounds
        if args.mode in ('ready', 'streamwait', 'windowupdate', 'windowlife', 'windowrace', 'loading', 'dma'):
            expected = args.rounds + (2 if args.mode == 'windowrace' else 0)
            require([row['round'] for row in rounds] == list(range(1, expected + 1)), 'all requested rounds required')
            require(all(row['children'] == 0 and row['jobs'] == 0 for row in rounds), 'child/job ledger did not drain')
            require(all({k: v for k, v in row.items() if k != 'round'} ==
                        {k: v for k, v in rounds[0].items() if k != 'round'} for row in rounds), 'round ledger drift')
        ledgers = []
        uart = []
        for line in log.splitlines():
            if line.startswith('K10 ledger UART ticks '):
                uart.append(int(line.split()[-1]))
            elif line.startswith('K10 ledger ') and ' ticks ' in line:
                words = line.split()
                ledgers.append(dict(round=int(words[2]), snapshot_ticks=int(words[4]), values=list(map(int, words[5:]))))
        record['ledger'] = {'schema': 'tests/k10/LEDGER.md', 'samples': ledgers,
                            'uart_ticks': uart, 'timebase_hz': 10000000,
                            'production_latency_evidence': False}
        expected_ledgers = len(rounds) + (2 if args.mode == 'ledgercontrol' else 1)
        require(len(ledgers) == expected_ledgers and ledgers[0]['round'] == 0, 'baseline and each full ledger required')
        require(all(len(row['values']) == 304 for row in ledgers), 'full ledger vector length')
        if args.mode == 'ledgercontrol':
            require([row['round'] for row in ledgers] == [0, 1, 2] and
                    ledgers[1]['values'] != ledgers[0]['values'] and
                    ledgers[2]['values'] == ledgers[0]['values'], 'live resource negative and drained positive required')
            record['expected_ledger_rejection'] = True
        else:
            require(all(row['values'] == ledgers[0]['values'] for row in ledgers), 'full owner ledger drift')
        if args.mode == 'windowrace':
            require(log.count('K5 COPY REVOKED AFTER FIRST PIECE') == 1 and
                    log.count('K5 KILL OBSERVES DYING LIVE WINDOW') == 1, 'both actual window interleavings required')
        if record['window_update_observer']:
            require(log.count('K10 WindowUpdate first piece held') == args.rounds, 'each update must reach the first real piece')
        if record['dma_observer']:
            marker = 'K7 observed submitted FS load cancel' if args.mode == 'loading' else 'K7 observed submitted Job output cancel'
            require(log.count(marker) == args.rounds, 'each cancellation must observe real Submitted DMA')
            record['dma_submission_observations'] = log.count(marker)
        record['passed'] = True
    except Exception as error:
        record['error'] = str(error)
        raise
    finally:
        (out / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    print('K10 exploration passed:', args.mode, '(not stage acceptance)')


if __name__ == '__main__':
    main()
