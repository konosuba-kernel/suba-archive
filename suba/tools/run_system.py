#!/usr/bin/env python3
"""Run a built or byte-transported system with its existing persistent disk."""
import argparse
import json
from pathlib import Path
import subprocess
import ram_launch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    args = parser.parse_args()
    snapshot = args.snapshot.resolve(strict=True)
    if (snapshot / 'deployment.json').exists():
        ram_launch.validate(snapshot)
    else:
        record = json.loads((snapshot / 'verification.json').read_text())
        if not record['built']:
            raise SystemExit('This snapshot did not finish building')
        if record.get('deployment'):
            ram_launch.validate(Path(record['deployment']))
    command = json.loads((snapshot / 'run.json').read_text())
    raise SystemExit(subprocess.call(command))


if __name__ == '__main__':
    main()
