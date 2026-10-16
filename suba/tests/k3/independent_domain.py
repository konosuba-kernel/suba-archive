#!/usr/bin/env python3
"""Independent K3 capability-domain probe; production files remain unchanged."""
import argparse
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
ANCHOR = '        if common::equal(role, "sleep") { return sleep_forever(); }'
ADDITION = '        if common::equal(role, "domain") {\n            if output != 257_usize { return 211; }\n            // The parent also has257, but it names its Job; ours is only a writer.\n            let end: syscall::Reply = services::job_end(output);\n            let kill: syscall::Reply = syscall::kill_child(output);\n            let foreign_close: syscall::Reply = syscall::close(258);\n            let foreign_kill: syscall::Reply = syscall::kill_child(260);\n            if end.status != abi::DENIED || kill.status != abi::DENIED ||\n                foreign_close.status != abi::BAD_HANDLE || foreign_kill.status != abi::BAD_HANDLE { return 212; }\n            let sent: syscall::Reply = services::write(output, "D", false);\n            if sent.status != abi::OK || sent.value != 1_usize { return 213; }\n            return 0;\n        }\n'

def worker_source(source):
    if source.count(ANCHOR) != 1:
        raise ValueError("worker domain injection anchor changed")
    return source.replace(ANCHOR, ADDITION + ANCHOR)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    source = out / "source"
    source.mkdir(parents=True, exist_ok=False)
    for name in ["abi", "kernel", "platform", "tests/k0", "tests/k3", "user/libsuba"]:
        shutil.copytree(ROOT / name, source / name)
    (source / "tests/k3/domain.vt").write_bytes((ROOT / "tests/k3/independent_domain.vt").read_bytes())
    worker = source / "tests/k3/worker.vt"
    worker.write_text(worker_source(worker.read_text()))
    sys.path.insert(0, str(ROOT / "tools"))
    import check_k3
    check_k3.ROOT = source
    sys.argv = ["check_k3.py", "--compiler", str(args.compiler.resolve()), "--out", str(out / "domain"), "--case", "domain"]
    check_k3.main()

if __name__ == "__main__":
    main()
