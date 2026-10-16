#!/usr/bin/env python3
"""Compile and exercise native text/editor/font code with independent Unicode/font oracles."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import re
import shutil
import struct
import subprocess

ROOT=Path(__file__).resolve().parents[1]
CORE=['user/text/utf8.vt','user/edit/buffer.vt','user/edit/motion.vt']
FONT=['user/text/font.vt','tools/fontpack/pack.vt']


def sha(data):return hashlib.sha256(data).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    compiler=args.compiler.resolve()
    files=[]
    for directory in ['user/text','user/edit','tools/fontpack','tests/k6','assets/unifont']:
        files.extend(path for path in (ROOT/directory).rglob('*') if path.is_file() and '__pycache__' not in path.parts)
    files.append(Path(__file__).resolve())
    snapshot=out/'source'
    for path in files:
        dest=snapshot/path.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
    spec=importlib.util.spec_from_file_location('model',snapshot/'tests/k6/model.py')
    model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
    cost_spec=importlib.util.spec_from_file_location('k6_cost',snapshot/'tests/k6/cost.py')
    costs=importlib.util.module_from_spec(cost_spec);cost_spec.loader.exec_module(costs)
    record=dict(compiler_sha256=sha(compiler.read_bytes()),inputs={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in files},
                builds=[],cases=[],passed=False,scope='native Linux execution of reusable K6 cores; no suba UI or FS integration claim')

    def build(name, sources, entry, assembly=True, mutation=None):
        folder=out/name;shutil.copytree(snapshot,folder)
        if mutation:
            path,old,new=mutation;p=folder/path;text=p.read_text()
            if text.count(old)!=1:raise RuntimeError('nonunique mutation')
            p.write_text(text.replace(old,new))
        manifest='format 1\nprofile linux-user\nentry '+entry+'\n'+''.join('source '+s+'\n' for s in sources)
        if assembly:manifest+='assembly tools/fontpack/linux.s0\n'
        (folder/'test.build').write_text(manifest+'output test.elf\n')
        cmd=['qemu-riscv64','-s','1048576',str(compiler),'build','test.build']
        p=subprocess.run(cmd,cwd=folder,capture_output=True,timeout=120)
        evidence=dict(name=name,command=cmd,returncode=p.returncode,stdout=p.stdout.decode(),stderr=p.stderr.decode(),mutation=mutation)
        record['builds'].append(evidence)
        if p.returncode:raise RuntimeError(name+': '+p.stderr.decode())
        evidence['elf_sha256']=sha((folder/'test.elf').read_bytes())
        evidence['metrics']=dict(re.findall(r'([a-z_]+)=([0-9]+)',p.stderr.decode()))
        if mutation is None:evidence['cost']=costs.measure(folder/'test.elf',folder,sources)
        return folder/'test.elf'

    def run(name, executable, data=b'', expected=b'', code=0, timeout=30):
        cmd=['qemu-riscv64','-s','1048576',str(executable)]
        p=subprocess.run(cmd,input=data,capture_output=True,timeout=timeout)
        passed=p.returncode==code and p.stdout==expected and not p.stderr
        record['cases'].append(dict(name=name,command=cmd,input_bytes=len(data),input_sha256=sha(data),
            expected_exit=code,actual_exit=p.returncode,expected_bytes=len(expected),actual_bytes=len(p.stdout),
            expected_sha256=sha(expected),actual_sha256=sha(p.stdout),stderr=p.stderr.decode(errors='replace'),passed=passed))
        if not passed:
            (out/(name+'.input')).write_bytes(data);(out/(name+'.actual')).write_bytes(p.stdout)
            (out/(name+'.expected')).write_bytes(expected)
            raise RuntimeError(name+' failed; preserved input/actual/expected')
        return p.stdout

    try:
        utf=build('utf8',['user/text/utf8.vt','tests/k6/transport.vt','tests/k6/utf8_probe.vt'],'test::utf8_probe::run')
        editor=build('editor',CORE+['tests/k6/transport.vt','tests/k6/editor_probe.vt'],'test::editor::run')
        resources=build('resources',CORE+FONT+['tests/k6/resources.vt'],'test::resources::run',False)
        pack=build('fontpack',FONT+['tools/fontpack/linux.vt'],'tool::fontpack_linux::run')
        glyphs=build('glyphs',['user/text/font.vt','tests/k6/transport.vt','tests/k6/font_probe.vt'],'test::font_probe::run')
        run('resource-ownership',resources)
        vectors=[b'',*map(lambda n:bytes([n]),range(256))]
        scalars=[0,1,0x7f,0x80,0x7ff,0x800,0xd7ff,0xe000,0xffff,0x10000,0x10ffff]
        vectors += [chr(c).encode() for c in scalars]
        invalid=[b'\xc0\x80',b'\xc1\xbf',b'\xe0\x80\x80',b'\xe0\x9f\xbf',b'\xed\xa0\x80',b'\xed\xbf\xbf',
            b'\xf0\x80\x80\x80',b'\xf0\x8f\xbf\xbf',b'\xf4\x90\x80\x80',b'\xf5\x80\x80\x80',b'\xff',
            b'\xe2A\xac',b'\xf0\x9fA\x80',b'abc\xc2']
        for data in [chr(c).encode() for c in scalars]:
            invalid += [data[:n] for n in range(1,len(data))]
        vectors += invalid
        rng=random.Random(0x6b6)
        random_scalars=[]
        while len(random_scalars)<10000:
            c=rng.randrange(0x110000)
            if not 0xd800<=c<=0xdfff:random_scalars.append(c)
        vectors.append(''.join(chr(c) for c in random_scalars).encode())
        for i,data in enumerate(vectors):
            try:
                text=data.decode('utf8');offset=0;expected=b''
                for c in text:
                    offset+=len(c.encode());expected+=struct.pack('<II',ord(c),offset)
                run(f'utf8-{i}',utf,data,expected)
            except UnicodeDecodeError as error:
                run(f'utf8-{i}',utf,data,struct.pack('<I',error.start),1)
        scenarios=[('mixed',128,'A中😀é\nZ'.encode(),[(1,1,4),(2,'文'.encode()),(3,1,1),(4,1),(3,4,0),(5,1,1),(2,b'X')]),
            ('invalid-boundary',32,'中😀'.encode(),[(1,1,3),(1,0,4),(2,b'\xff')]),
            ('no-memory',4,'中'.encode(),[(2,'文'.encode()),(1,0,3),(2,'😀'.encode()),(2,b'x')]),
            ('open-invalid',64,b'valid\xf0\x80\x80\x80',[]),('open-no-memory',2,'中'.encode(),[]),
            ('limit-exact',model.MAX_BYTES,b'x'*model.MAX_BYTES,[(2,b'x'),(1,model.MAX_BYTES-3,model.MAX_BYTES),(2,'中'.encode())]),
            ('open-limit',model.MAX_BYTES,b'x'*(model.MAX_BYTES+1),[])]
        alphabet=['a','Z','中','文','😀','\n','\r','e','́','\0','\ufeff']
        for case in range(24):
            initial=''.join(rng.choice(alphabet) for _ in range(15)).encode()
            oracle=model.Model(192,initial);actions=[]
            for step in range(100):
                tag=rng.randrange(1,6)
                if tag==1:
                    points=model.boundaries(oracle.text);action=(1,rng.choice(points),rng.choice(points))
                elif tag==2:action=(2,''.join(rng.choice(alphabet) for _ in range(rng.randrange(7))).encode())
                elif tag==3:action=(3,rng.randrange(6),rng.randrange(2))
                elif tag==4:action=(4,rng.randrange(2))
                else:action=(5,rng.randrange(2),rng.randrange(2))
                actions.append(action);oracle.apply(action)
            scenarios.append(('model-'+str(case),192,initial,actions))
        for name,capacity,initial,actions in scenarios:
            data,expected=model.editor_case(capacity,initial,actions)
            run('editor-'+name,editor,data,expected,timeout=60)
        source=(snapshot/'assets/unifont/unifont-17.0.04.hex').read_bytes()
        expected=bytearray(2162704);expected[:16]=b'SUBAFNT1'+struct.pack('<II',65536,16)
        source_glyphs={}
        for line in source.splitlines():
            code,bits=line.split(b':');cp=int(code,16);bitmap=bytes.fromhex(bits.decode());source_glyphs[cp]=bitmap
            stride=len(bitmap)//16;expected[16+cp]=stride*8
            for y in range(16):expected[65552+cp*32+y*2:65552+cp*32+y*2+stride]=bitmap[y*stride:(y+1)*stride]
        packed=run('fontpack-source',pack,source,bytes(expected),timeout=60)
        run('fontpack-determinism',pack,source,packed,timeout=60)
        if packed!=(snapshot/'assets/unifont/suba-bmp.fnt').read_bytes():raise RuntimeError('shipped font differs from native pack')
        (out/'suba-bmp.fnt').write_bytes(packed)
        invalid_hex=[b'',b'0041:XYZ\n',b'0041:'+b'0'*31+b'\n',b'D800:'+b'0'*32+b'\n',
            b'0041:'+b'0'*32+b'\n0041:'+b'0'*32+b'\n',b'0042:'+b'0'*32+b'\n0041:'+b'0'*32+b'\n',
            b'10000:'+b'0'*32+b'\n']
        for i,data in enumerate(invalid_hex):run('fontpack-invalid-'+str(i),pack,data,b'',1)
        run('fontpack-limit',pack,b'X'*5242881,b'',3)
        query=[0x20,0x41,0x7e,0x4e2d,0x6587,0x3400,0x4dbf,0x4e00,0x9fff,0xfffd,0x1f600,0x10ffff,0xd800]
        box=bytes.fromhex('00007ffe4002400240024002400240024002400240024002400240027ffe0000')
        rendered=b''
        for cp in query:
            bitmap=source_glyphs.get(cp,box);missing=cp not in source_glyphs;stride=len(bitmap)//16
            rendered+=struct.pack('<II',16 if missing else stride*8,int(missing))
            for y in range(16):rendered+=struct.pack('<I',int.from_bytes(bitmap[y*stride:(y+1)*stride],'big') << (8 if stride==1 else 0))
        pixels=run('glyph-pixels',glyphs,packed+b''.join(struct.pack('<I',cp) for cp in query),rendered)
        (out/'glyphs.bin').write_bytes(pixels)
        for name,offset,value in [('magic',0,0),('width',16+0x41,9),('surrogate',16+0xd800,16)]:
            changed=bytearray(packed);changed[offset]=value;run('font-invalid-'+name,glyphs,bytes(changed),b'',1)
        bad_utf=build('negative-overlong',['user/text/utf8.vt','tests/k6/transport.vt','tests/k6/utf8_probe.vt'],
            'test::utf8_probe::run',mutation=('user/text/utf8.vt','if value < minimum || !scalar(value)', 'if !scalar(value)'))
        run('negative-overlong-observed',bad_utf,b'\xe0\x80\x80',struct.pack('<II',0,3))
        bad_edit=build('negative-capacity',CORE+['tests/k6/transport.vt','tests/k6/editor_probe.vt'],
            'test::editor::run',mutation=('user/edit/buffer.vt','if input.len > before.capacity - kept { return Edit::NoMemory; }',
                'if input.len > before.capacity - kept { (*document).anchor = 0; return Edit::NoMemory; }'))
        data,expected_bad=model.editor_case(4,'中'.encode(),[(2,'文'.encode())])
        changed=expected_bad[:-23]+struct.pack('<5I',4,0,3,0,3)+'中'.encode()
        run('negative-state-damage-observed',bad_edit,data,changed)
        limited=build('version-limit',CORE+['tests/k6/transport.vt','tests/k6/editor_probe.vt'],
            'test::editor::run',mutation=('user/edit/buffer.vt',
                'const VERSION_MAX: usize = 18446744073709551615;', 'const VERSION_MAX: usize = 2;'))
        version_actions=[(2,b''),(1,0,0),(2,b'X'),(4,1)]
        data,_=model.editor_case(64,'A中'.encode(),version_actions)
        state=model.Model(64,'A中'.encode());expected=state.frame()
        for action in version_actions[:-1]:expected+=state.frame(state.apply(action))
        expected+=state.frame(6)
        run('version-exhaustion-test-copy',limited,data,expected)
        record['font']=dict(glyph_count=len(source_glyphs),source_bytes=len(source),packed_bytes=len(packed),packed_sha256=sha(packed),
            cjk_basic_complete=all(cp in source_glyphs for cp in range(0x4e00,0xa000)),
            cjk_extension_a_complete=all(cp in source_glyphs for cp in range(0x3400,0x4dc0)))
        record['passed']=True
    finally:
        (out/'verification.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(dict(passed=True,cases=len(record['cases']),record=str(out/'verification.json'))))


if __name__=='__main__':main()
