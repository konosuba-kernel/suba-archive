#!/usr/bin/env python3
"""Bounded host-side device protocol probe, not a suba driver or boot test."""
import pathlib, tempfile, subprocess, socket, json, struct, time
OUT=pathlib.Path(__file__).resolve().parent
log=[]
with tempfile.TemporaryDirectory(prefix='suba-ramfb-') as tmp:
    qp=str(pathlib.Path(tmp)/'qmp.sock')
    disk=pathlib.Path(tmp)/'disk.raw'
    with disk.open('wb') as f:f.truncate(1024*1024*1024)
    cmd=['qemu-system-riscv64','-machine','virt,aclint=off,aia=none,acpi=off,iommu-sys=off','-accel','tcg','-cpu','rv64','-smp','1','-m','512M','-bios','default','-S','-global','virtio-mmio.force-legacy=false','-drive',f'file={disk},format=raw,if=none,id=subadisk,cache=writeback','-device','virtio-blk-device,drive=subadisk,bus=virtio-mmio-bus.0','-device','virtio-keyboard-device,bus=virtio-mmio-bus.2','-device','virtio-tablet-device,bus=virtio-mmio-bus.3','-device','ramfb','-display','none','-serial','none','-monitor','none','-qtest','stdio','-qtest-log','/dev/null','-qmp',f'unix:{qp},server=on,wait=off']
    p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        for _ in range(100):
            if pathlib.Path(qp).exists():break
            if p.poll() is not None:raise RuntimeError(p.stderr.read())
            time.sleep(.01)
        s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.connect(qp);q=s.makefile('rwb');banner=json.loads(q.readline())
        def qmp(execute,arguments=None):
            r={'execute':execute}
            if arguments is not None:r['arguments']=arguments
            q.write((json.dumps(r)+'\n').encode());q.flush()
            while True:
                v=json.loads(q.readline())
                if 'return' in v or 'error' in v:
                    log.append({'qmp':r,'result':v});return v
        def qt(line,record=True):
            p.stdin.write(line+'\n');p.stdin.flush();r=p.stdout.readline().strip()
            if record:log.append({'qtest':line,'result':r})
            if not r.startswith('OK'):raise RuntimeError((line,r))
            return r
        def rd(addr):return int(qt(f'readb {addr:#x}',False).split()[1],16)
        qmp('qmp_capabilities')
        # Select FW_CFG_FILE_DIR, writew stores host value little-endian.
        qt('writew 0x10100008 0x1900')
        count=int.from_bytes(bytes(rd(0x10100000) for _ in range(4)),'big')
        assert 0<count<256,count
        entries=[]
        for _ in range(count):
            raw=bytes(rd(0x10100000) for _ in range(64))
            size,selector,_=struct.unpack('>IHH',raw[:8]);name=raw[8:].split(b'\0',1)[0].decode()
            entries.append({'name':name,'size':size,'selector':selector})
        log.append({'fw_cfg_directory':entries})
        ent=next(e for e in entries if e['name']=='etc/ramfb');assert ent['size']==28
        fb=0x90000000;cfg=0x81000000;dma=0x81000100;w=64;h=32
        # DRM_FORMAT_XRGB8888='XR24'; bytes in LE framebuffer are B,G,R,X.
        cfgbytes=struct.pack('>QIIIII',fb,0x34325258,0,w,h,w*4)
        qt(f'write {cfg:#x} {len(cfgbytes)} 0x{cfgbytes.hex()}')
        desc=struct.pack('>IIQ',(ent['selector']<<16)|0x18,len(cfgbytes),cfg)
        qt(f'write {dma:#x} {len(desc)} 0x{desc.hex()}')
        pixel=bytes([0,0,255,0])*(w*h)
        qt(f'write {fb:#x} {len(pixel)} 0x{pixel.hex()}',False)
        log.append({'framebuffer_write':{'address':hex(fb),'bytes':len(pixel),'pixel':'B=0,G=0,R=255,X=0'}})
        qt('writeq 0x10100010 '+hex(int.from_bytes(dma.to_bytes(8,'big'),'little')))
        control=qt(f'readl {dma:#x}');assert int(control.split()[1],16)==0
        snap=str(pathlib.Path(tmp)/'screen.ppm');r=qmp('screendump',{'filename':snap});assert 'return' in r,r
        b=pathlib.Path(snap).read_bytes();head=b'P6\n64 32\n255\n';assert b.startswith(head),b[:50]
        assert b[len(head):]==bytes([255,0,0])*(w*h)
        log.append({'assertion':'64x32 XRGB8888 red framebuffer rendered to exact RGB pixels','pass':True})
        # One-time configuration remains in effect after direct framebuffer update.
        qt(f'write {fb:#x} 4 0x00ff0000')
        qmp('screendump',{'filename':snap});b=pathlib.Path(snap).read_bytes();assert b[len(head):len(head)+3]==bytes([0,255,0])
        log.append({'assertion':'direct framebuffer change visible without GPU transfer/flush or reconfiguration','pass':True})
        log.append({'qtree':qmp('human-monitor-command',{'command-line':'info qtree'})})
        qmp('quit');p.wait(timeout=5)
        (OUT/'platform-ramfb-probe.json').write_text(json.dumps({'command':cmd,'qmp_banner':banner,'log':log,'returncode':p.returncode,'stderr':p.stderr.read()},ensure_ascii=False,indent=2)+'\n')
        print('PASS: ramfb directory, DMA setup, exact red output, direct green pixel update')
    finally:
        if p.poll() is None:p.terminate();p.wait(timeout=5)
