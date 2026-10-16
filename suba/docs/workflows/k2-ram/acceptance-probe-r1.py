from pathlib import Path
import sys,shutil,json,hashlib
ROOT=Path('/home/mii/code/konOSuba/suba')
sys.path.insert(0,str(ROOT/'tools'))
import check_ram_boot as h
out=Path(__file__).resolve().parent
compiler=(ROOT/'../biomiya/build/layout-p4-r1/e3.elf').resolve()
report={'candidate':'54340df9b0e9cfba40bd872fdde6c03a83a0e31497c27b8b7008c8020eccb2e4','cases':[],'passed':False}
try:
 for name in ['omit-bootinfo-reservations','invalid-raw-info-pointer','overlap-sources']:
  source=ROOT/('build/k2-ram-k0-r1/valid' if name=='invalid-raw-info-pointer' else 'build/k2-ram-i-r1/reserved-holes')
  work=out/name
  shutil.copytree(source,work)
  item={'name':name,'commands':[]};report['cases'].append(item)
  if name=='omit-bootinfo-reservations':
   h.replace(work/'kernel/ram.vt','while i < info.reserved_count {','while i < 0_usize {')
  if name=='invalid-raw-info-pointer':
   h.replace(work/'tests/k0/boot.vt','machine::enter(config::KERNEL_ENTRY, core::addr(core::slice_of(INFO).data));','machine::enter(config::KERNEL_ENTRY, 0xfffffffffffffff8_usize);')
  if name=='overlap-sources':
   h.replace(work/'tests/k0/boot.vt','put(abi::BOOT_INFO_RESERVATION_COUNT, 2, 4);','put(abi::BOOT_INFO_RESERVATION_COUNT, 3, 4);')
   h.replace(work/'tests/k0/boot.vt','    // SAFETY: kernel ELF is preloaded by the test harness.', '    put(abi::BOOT_INFO_RESERVATIONS + 32_usize, 0x81202fff, 8);\n    put(abi::BOOT_INFO_RESERVATIONS + 40_usize, 2, 8);\n    // SAFETY: kernel ELF is preloaded by the test harness.')
   dts=(ROOT/'build/k2-ram-i-r1/reserved.dts').read_text().replace('reg = <0 0x81202005 0 0x2000>;','reg = <0 0x81202005 0 0x2000>, <0 0x81001fff 0 2>;')
   (work/'overlap.dts').write_text(dts)
   item['commands'].append(h.run(['dtc','-I','dts','-O','dtb','overlap.dts','-o','overlap.dtb'],work))
  def build(manifest):
   output=work/('build/kernel.elf' if manifest=='kernel/kernel.build' else 'build/boot.elf')
   output.unlink(missing_ok=True)
   item['commands'].append(h.run(['qemu-riscv64','-s','1048576',str(compiler),'build',manifest],work))
  build('kernel/kernel.build')
  kernel=h.image(work/'build/kernel.elf',0x80400000,0x4000000)
  if name!='invalid-raw-info-pointer':
   h.write_ram_config(work,True,kernel['end'])
   build('kernel/kernel.build')
   final=h.image(work/'build/kernel.elf',0x80400000,0x4000000)
   h.require(final['end']==kernel['end'],'unexpected end drift');kernel=final
  (work/'config.vt').write_text('module test::config;\npub const MAGIC: usize = 0x314f464e49425553;\n'+f'pub const KERNEL_END: usize = {kernel["end"]};\npub const KERNEL_ENTRY: usize = {kernel["entry"]};\n')
  build('boot.build')
  command=['qemu-system-riscv64','-machine','virt','-accel','tcg','-m','512M','-smp','1','-nographic','-bios',str(h.FIRMWARE),'-kernel',str(work/'build/boot.elf'),'-device',f'loader,file={work}/build/kernel.elf','-device','ramfb','-no-reboot']
  if name!='invalid-raw-info-pointer':command+=['-dtb',str(work/'overlap.dtb') if name=='overlap-sources' else str(ROOT/'build/k2-ram-i-r1/reserved.dtb')]
  reason={'omit-bootinfo-reservations':26,'invalid-raw-info-pointer':1}.get(name)
  marker=f'suba kernel panic reason={reason}\n' if reason else 'suba kernel K0: handoff accepted\n'
  forbidden=('handoff accepted','RAM: verified','!') if reason else ('panic','!')
  item['execution']=h.observe(command,marker,forbidden,timeout=90)
  item['expected_events']=['suba K0 boot: entering kernel']+([marker.strip()] if reason else ['suba K2b RAM: verified',marker.strip()])
  item['events']=[s for s in item['execution']['log'].splitlines() if s.startswith(('suba ','!'))]
  item['inputs']={str(p.relative_to(work)):hashlib.sha256(p.read_bytes()).hexdigest() for p in work.rglob('*') if p.is_file() and p.suffix in ['.vt','.s0','.build','.dtb']}
  item['kernel']=kernel
  item['passed']=item['execution']['passed'] and item['events']==item['expected_events']
  (work/'serial.log').write_text(item['execution']['log'])
  h.require(item['passed'],name+': unexpected behavior')
  print(name+': passed',flush=True)
 report['passed']=True
finally:
 (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
