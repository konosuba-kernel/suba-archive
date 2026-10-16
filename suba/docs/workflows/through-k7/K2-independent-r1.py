#!/usr/bin/env python3
"""Reviewer-only hardware counterexample: user store to its readonly argument page."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
source=(root/'tools/check_k2.py').read_text()
source=source.replace('from check_kernel_entry import', 'import sys\nsys.path.insert(0, '+repr(str(root/'tools'))+')\nfrom check_kernel_entry import')
source=source.replace('ROOT = Path(__file__).resolve().parents[1]', 'ROOT = Path('+repr(str(root))+')')
source=source.replace("'guard'", "'argument-write'")
assert source.count("'argument-write':0x3feff000")==1
source=source.replace("'argument-write':0x3feff000", "'argument-write':0x3fe00000")
assert source.count("'argument-write':'ld x5, 0(x10)'")==1
source=source.replace("'argument-write':'ld x5, 0(x10)'", "'argument-write':'sb x0, 0(x10)'")
assert source.count("'argument-write':13")==1
source=source.replace("'argument-write':13", "'argument-write':15")
runner=out/'runner.py';runner.write_text(source)
command=[sys.executable,str(runner),'--compiler',str(a.compiler.resolve()),'--out',str(out/'run'),'--case','argument-write']
run=subprocess.run(command,cwd=root,capture_output=True,text=True,timeout=300)
record={'reviewer':'/root','candidate_sha256':hashlib.sha256((root/'docs/workflows/through-k7/K2-candidate-r1.json').read_bytes()).hexdigest(),'command':command,'runner_sha256':hashlib.sha256(runner.read_bytes()).hexdigest(),'returncode':run.returncode,'stdout':run.stdout,'stderr':run.stderr,'passed':run.returncode==0}
(out/'independent.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record));sys.exit(run.returncode)
