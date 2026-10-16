"""Compile the generic RAM boot once from frozen inputs, independent of kernel ELF."""
import json
import shutil
import subprocess
from check_k2 import sha


def build(root, compiler, out, record, reuse=None):
    manifest = (root / 'boot/ram.build').read_text()
    names = [line.split(' ', 1)[1] for line in manifest.splitlines()
             if line.startswith(('source ', 'assembly '))] + ['boot/ram.build']
    for name in names:
        target = out / name
        data = (root / name).read_bytes()
        if target.exists() and target.read_bytes() != data:
            raise ValueError('fixed boot input changed: ' + name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    inputs = {name: sha(out / name) for name in names}
    target = out / 'build/ram-boot.elf'
    target.parent.mkdir(exist_ok=True)
    if reuse and (reuse / 'verification.json').exists():
        previous = json.loads((reuse / 'verification.json').read_text())
        old = previous.get('fixed_boot', {})
        source = reuse / 'build/ram-boot.elf'
        if previous.get('compiler_sha256') == sha(compiler) and old.get('inputs') == inputs:
            if sha(source) != old['sha256']:
                raise ValueError('fixed boot cached ELF changed')
            shutil.copyfile(source, target)
            record['fixed_boot'] = dict(old, reused_from=str(reuse))
            return target
    command = ['qemu-riscv64', '-s', '1048576', str(compiler), 'build', 'boot/ram.build']
    result = subprocess.run(command, cwd=out, capture_output=True, timeout=600)
    (out / 'ram-boot-compile.log').write_bytes(result.stdout + result.stderr)
    record['fixed_boot'] = {'inputs': inputs, 'command': command, 'returncode': result.returncode}
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace'))
    record['fixed_boot'].update(sha256=sha(target), bytes=target.stat().st_size)
    return target
