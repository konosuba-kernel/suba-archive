#!/usr/bin/env python3
"""Counterexamples for the serial marker observer; no kernel behavior is assumed."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from check_kernel_entry import observe

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--record', type=Path, required=True)
args = parser.parse_args()
if args.record.exists():
    raise SystemExit('record already exists')
cases = []
for name, source, expected in [
    ('stable-marker', "print('READY', flush=True); time.sleep(2)", True),
    ('late-failure', "print('READY', flush=True); time.sleep(.05); print('PANIC', flush=True); time.sleep(2)", False),
    ('early-exit', "print('READY', flush=True)", False),
]:
    result = observe([sys.executable, '-c', 'import time; '+source], 'READY', 'PANIC', timeout=3)
    cases.append({'name': name, 'expected_passed': expected, 'execution': result})
    if result['passed'] != expected:
        raise SystemExit(f'observer misclassified {name}')
record = {'passed': True, 'cases': cases, 'observer_sha256': hashlib.sha256(
    (Path(__file__).parent/'check_kernel_entry.py').read_bytes()).hexdigest()}
args.record.parent.mkdir(parents=True, exist_ok=True)
args.record.write_text(json.dumps(record, indent=2)+'\n')
print('3/3 observer counterexamples passed')
