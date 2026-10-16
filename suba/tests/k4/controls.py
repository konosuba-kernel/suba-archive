"""Snapshot-only observation/IRQ delay for reproducible cancellation windows.

DMA case masks the real PLIC source before the second data submission. The real
parent U process observes the state and invokes kill_child. The next U return
restores PLIC delivery, and a real U external trap must precede consumption. No completion is fabricated and production transport is unchanged.
"""
from pathlib import Path


def install_cancel(out: Path, case: str):
    state = out / 'kernel/fs/state.vt'
    state.write_text(state.read_text().replace('module kernel::fs;', 'module kernel::fs;\nimport kernel::device::hub;', 1))
    hub = out / 'kernel/device/hub.vt'
    hub.write_text(hub.read_text() + '''
// TEST ONLY: retain a real submitted request until a user kill syscall releases IRQ.
static mut TEST_RELEASE: bool = false;
static mut TEST_EXPECT: bool = false;
static mut TEST_BASE: usize = 0;
pub unsafe fn test_pause(pause: bool) -> () {
    unsafe {
        if pause { io::write32(devices::MMIO_OFFSET + devices::PLIC_ENABLE + 0x80_usize, 0); }
        else { TEST_RELEASE = true; }
    }
    return ();
}
pub unsafe fn test_before_user() -> () {
    unsafe {
        if TEST_RELEASE {
            TEST_RELEASE = false;
            TEST_EXPECT = true;
            TEST_BASE = USER_TRAPS;
            io::write32(devices::MMIO_OFFSET + devices::PLIC_ENABLE + 0x80_usize, ENABLED);
            // Re-evaluate the pending line after changing enables. QEMU's PLIC
            // model may defer this update until a threshold write or new input.
            io::write32(devices::MMIO_OFFSET + devices::PLIC_CONTEXT, 0);
        }
    }
    return ();
}
''')
    text = hub.read_text()
    anchor = '            if source != BLOCK_IRQ || !block::interrupt()'
    if text.count(anchor) == 0:
        # K5's shared hub dispatches both block and input IRQs. The observation
        # still precedes that real claim; no transport completion is fabricated.
        anchor = '            if source == BLOCK_IRQ { if !block::interrupt()'
    assert text.count(anchor) == 1
    text = text.replace(anchor, '''            if TEST_EXPECT { TEST_EXPECT = false; }
''' + anchor)
    # A syscall can win the race against asynchronous external-interrupt delivery.
    # Keep the designated completion unavailable to schedule's ordinary claim path
    # until a real U external trap has happened; no used-ring polling is injected.
    service = 'pub unsafe fn service() -> bool {\n    unsafe {'
    assert text.count(service) == 1
    text = text.replace(service, service + '\n        if TEST_EXPECT && USER_TRAPS <= TEST_BASE { return true; }')
    hub.write_text(text)
    entry = out / 'kernel/entry.vt'
    text = entry.read_text()
    anchor = '                    machine::activate(selected.token);'
    assert text.count(anchor) == 1
    entry.write_text(text.replace(anchor, '                    hub::test_before_user();\n' + anchor))
    if case == 'cancel_no_irq':
        path = out / 'kernel/trap.s0'
        text = path.read_text()
        assert text.count('addi x5, x0, 544') == 2
        path.write_text(text.replace('addi x5, x0, 544', 'addi x5, x0, 32'))
    predicate = 'Phase::Input' 
    if case == 'cancel_reserve':
        predicate = 'Phase::Reserve'
    if case in ('cancel_dma', 'cancel_no_irq'):
        predicate = 'Phase::Writing'
        path = out / 'kernel/fs/transfer.vt'
        text = path.read_text()
        anchor = '        if !block::submit(block::Command::Write(DISK_BASE + BLOCK_IDS[IO_INDEX] as usize))'
        assert text.count(anchor) == 1
        text = text.replace(anchor, '''        if IO_INDEX == 1_usize {
            hub::test_pause(true);
        }
''' + anchor)
        path.write_text(text)
    helper = '''
// TEST ONLY: an observation of the real active transaction, never an injected result.
pub unsafe fn test_stage() -> usize {
    unsafe {
        if ACTIVE == 16_usize { return 0; }
        match PHASE {
'''
    phases = ['Start', 'Resolve', 'ResolveOther', 'Create', 'Remove', 'Enumerate',
              'Input', 'Locate', 'Reserve', 'Read', 'Reading', 'Output',
              'PrepareWrite', 'EdgeReading', 'Writing', 'Commit', 'SyncScan',
              'Encode', 'SyncWriting', 'Flush', 'Flushing']
    for phase in phases:
        if 'Phase::' + phase == predicate:
            condition = {
                'cancel_pre': 'COPIED < 32768_usize && !SUBMITTED',
                'cancel_reserve': 'RESERVED_COUNT > 0_usize && RESERVED_COUNT < REQUIRED && !SUBMITTED',
                'cancel_dma': 'IO_INDEX == 1_usize && SUBMITTED',
                'cancel_no_irq': 'IO_INDEX == 1_usize && SUBMITTED',
            }[case]
            helper += f'            Phase::{phase} => {{ if {condition} {{ return 1; }} }},\n'
        else:
            helper += f'            Phase::{phase} => {{}},\n'
    helper += '''        }
        return 0;
    }
}
pub unsafe fn test_release() -> bool {
    unsafe {
        if test_stage() != 1_usize { return false; }
'''
    if case in ('cancel_dma', 'cancel_no_irq'):
        helper += '''        match block::state() {
            block::State::Submitted => {},
            block::State::Offline => { return false; }, block::State::Idle => { return false; },
            block::State::Completed => { return false; }, block::State::Failed => { return false; }
        }
        hub::test_pause(false);
'''
    helper += '''        return true;
    }
}
'''
    fs = out / 'kernel/fs/worker.vt'
    fs.write_text(fs.read_text() + helper)
    dispatch = out / 'kernel/dispatch_call.vt'
    text = dispatch.read_text()
    anchor = '                                if !process::terminate(target, abi::CANCELLED)'
    assert text.count(anchor) == 1
    text = text.replace(anchor, '''                                if !fs::test_release() { return false; }
                                machine::text("suba K4: observed user cancel window\\n");
''' + anchor)
    anchor = '        if operation == abi::SYS_STATS {'
    assert text.count(anchor) == 1
    text = text.replace(anchor, anchor + '\n            if args[0_usize] == 100_usize { return answer(id, abi::OK, fs::test_stage()); }')
    dispatch.write_text(text)
