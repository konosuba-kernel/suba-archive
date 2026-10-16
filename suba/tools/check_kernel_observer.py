#!/usr/bin/env python3
"""Counterexamples for the serial marker observer; no kernel behavior is assumed."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from check_kernel_entry import observe, terminal_matches

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--record', type=Path, required=True)
args = parser.parse_args()
if args.record.exists():
    raise SystemExit('record already exists')
cases = []
for name, source, expected in [
    ('stable-marker', "print('READY', flush=True); time.sleep(2)", True),
    ('late-failure', "print('READY', flush=True); time.sleep(.05); print('PANIC', flush=True); time.sleep(2)", False),
    ('late-emergency', "print('READY', flush=True); time.sleep(.05); print('!0000000000000002:0000000080400000:0000000000000000', flush=True); time.sleep(2)", False),
    ('early-exit', "print('READY', flush=True)", False),
]:
    result = observe([sys.executable, '-c', 'import time; '+source], 'READY', ('PANIC', '!'), timeout=3)
    cases.append({'name': name, 'expected_passed': expected, 'execution': result})
    if result['passed'] != expected:
        raise SystemExit(f'observer misclassified {name}')
boot = 'suba K0 boot: entering kernel\n'
ok = 'suba kernel K0: handoff accepted\n'
panic = 'suba kernel panic reason=1\n'
fault = '!0000000000000002:0000000080400000:0000000000000000\n'
terminal_cases = []
for path, terminal in [('valid', ok), ('bad-magic', panic), ('trusted-fault', fault)]:
    samples = [('one-outcome', boot+terminal, True),
               ('duplicate-outcome', boot+terminal+terminal, False),
               ('before-boot', terminal+boot, False),
               ('boot-panic-after', boot+terminal+'suba K0 boot panic\n', False)]
    for other in [ok, panic, fault]:
        if other != terminal:
            samples.append(('different-outcome-after', boot+terminal+other, False))
    for name, text, expected in samples:
        actual = terminal_matches(text, path)
        terminal_cases.append({'path': path, 'name': name, 'text': text,
                               'expected': expected, 'actual': actual})
        if actual != expected:
            raise SystemExit(f'terminal misclassified {path}/{name}')
for text in [boot+'!0000000000000002:', boot+'!0000000000000003:0000000080400000:0000000000000000\n']:
    actual = terminal_matches(text, 'trusted-fault')
    terminal_cases.append({'path': 'trusted-fault', 'name': 'incomplete-or-wrong-cause',
                           'text': text, 'expected': False, 'actual': actual})
    if actual:
        raise SystemExit('accepted incomplete or wrong-cause fault')
record = {'passed': True, 'cases': cases, 'terminal_cases': terminal_cases, 'observer_sha256': hashlib.sha256(
    (Path(__file__).parent/'check_kernel_entry.py').read_bytes()).hexdigest()}
args.record.parent.mkdir(parents=True, exist_ok=True)
args.record.write_text(json.dumps(record, indent=2)+'\n')
print(f'{len(cases)} process observations and {len(terminal_cases)} terminal checks passed')
