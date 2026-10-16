#!/usr/bin/env python3
"""Independent K6 reviewer probes; requires an existing fresh check_k6 build directory."""
import hashlib,json,struct,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[3]
out=Path(sys.argv[1]).resolve()
editor=out/'editor/test.elf'; utf=out/'utf8/test.elf'
def frame(text,cursor,anchor,version=0,code=0):
    raw=text.encode();return struct.pack('<5I',code,version,cursor,anchor,len(raw))+raw
def select(a,c):return b'\1'+struct.pack('<II',a,c)
def replace(raw):return b'\2'+struct.pack('<I',len(raw))+raw
def initial(cap,text):
    raw=text.encode();return struct.pack('<II',cap,len(raw))+raw
cases=[
 ('zero-capacity',editor,initial(0,'')+replace(b'X')+b'\4\1',
  frame('',0,0)+frame('',0,0,code=4)+frame('',0,0)),
 ('full-storage-reverse-selection',editor,
  initial(8,'A中😀')+select(8,1)+replace('文'.encode())+select(2,4),
  frame('A中😀',8,8)+frame('A中😀',1,8)+frame('A文',4,4,1)+frame('A文',4,4,1,2)),
 ('supplementary-delete-around-gap',editor,
  initial(32,'😀\0中\n')+select(4,4)+b'\4\0'+b'\4\1'+b'\3\3\0'+b'\4\0',
  frame('😀\0中\n',9,9)+frame('😀\0中\n',4,4)+frame('😀中\n',4,4,1)+frame('中\n',0,0,2)+frame('中\n',3,3,2)+frame('中',3,3,3)),
 ('invalid-after-valid-prefix',utf,b'\0\xf4\x90\x80\x80',struct.pack('<I',1)),
]
results=[]
for name,elf,data,expected in cases:
    p=subprocess.run(['qemu-riscv64','-s','1048576',str(elf)],input=data,capture_output=True,timeout=30)
    code=1 if name=='invalid-after-valid-prefix' else 0
    passed=p.returncode==code and not p.stderr and p.stdout==expected
    results.append(dict(name=name,passed=passed,returncode=p.returncode,input_sha256=hashlib.sha256(data).hexdigest(),actual_sha256=hashlib.sha256(p.stdout).hexdigest(),expected_sha256=hashlib.sha256(expected).hexdigest()))
    if not passed:print(name,p.returncode,p.stdout.hex(),expected.hex(),p.stderr)
record=dict(reviewer='/root',candidate_sha256=hashlib.sha256((root/'docs/workflows/through-k7/K6-candidate-r1.json').read_bytes()).hexdigest(),cases=results,passed=all(r['passed'] for r in results))
(out/'independent.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record));sys.exit(0 if record['passed'] else 1)
