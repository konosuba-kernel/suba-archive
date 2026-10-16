"""Audit this frozen S-next backend's exact function prologues and direct call graph."""
import re
import struct


def measure(elf, folder, sources):
    functions=[];imports={}
    for source in sources:
        text=(folder/source).read_text()
        module=re.search(r'(?m)^module ([\w:]+);',text)[1]
        imports.setdefault(module,{})
        for imported,alias in re.findall(r'(?m)^import ([\w:]+)(?: as (\w+))?;',text):
            imports[module][alias or imported.split('::')[-1]]=imported
        for found in re.finditer(r'(?m)^(?:pub )?(?:unsafe )?fn (\w+)\(',text):
            begin=text.index('{',found.end());end=begin+1;depth=1
            while depth:
                if text[end]=='{':depth+=1
                if text[end]=='}':depth-=1
                end+=1
            functions.append(dict(name=module+'::'+found[1],module=module,source=source,body=text[begin+1:end-1]))
    data=elf.read_bytes();phoff=struct.unpack_from('<Q',data,32)[0]
    width,count=struct.unpack_from('<HH',data,54);segments=[]
    for index in range(count):
        kind,flags,offset,address,_,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',data,phoff+index*width)
        if kind==1:
            segments.append(dict(flags=flags,file_bytes=filesz,memory_bytes=memsz,bss_bytes=memsz-filesz))
            if flags==5:text=data[offset:offset+filesz];base=address
    words=struct.unpack('<'+'I'*(len(text)//4),text);prologues=[]
    for i,word in enumerate(words):
        if word!=0x00010f13:continue
        j=i+1;value=0
        while words[j]!=0x41f10133:
            instruction=words[j];opcode=instruction&127;rd=(instruction>>7)&31
            f3=(instruction>>12)&7;rs1=(instruction>>15)&31;immediate=instruction>>20
            if opcode!=19 or rd!=31:raise RuntimeError('unknown prologue')
            if f3==0 and rs1 in (0,31):
                if immediate&0x800:immediate-=4096
                value=(0 if rs1==0 else value)+immediate
            elif f3==1 and rs1==31 and immediate==12:value<<=12
            else:raise RuntimeError('unknown frame constant')
            j+=1
        if value<=0 or value%16:raise RuntimeError('invalid frame')
        prologues.append((base+i*4,value))
    if len(prologues)!=len(functions):raise RuntimeError('declaration/prologue count mismatch')
    names={fn['name'] for fn in functions};entries={}
    for function,(address,frame) in zip(functions,prologues):
        body=re.sub(r'//[^\n]*','',function.pop('body'));body=re.sub(r'"(?:\\.|[^"\\])*"','""',body)
        calls=set()
        for call in re.findall(r'(?<![\w:])((?:\w+::)*\w+)\s*\(',body):
            if '::' in call:
                alias,rest=call.split('::',1);target=imports[function['module']].get(alias,alias)+'::'+rest
            else:target=function['module']+'::'+call
            if target in names:calls.add(target)
        function.update(address=address,frame_bytes=frame,calls=sorted(calls));entries[function['name']]=function
    def chain(name,ancestors=()):
        if name in ancestors:raise RuntimeError('recursive source graph')
        children=[chain(child,ancestors+(name,)) for child in entries[name]['calls']]
        size,path=max(children,default=(0,[]),key=lambda item:item[0])
        return entries[name]['frame_bytes']+size,[name]+path
    public={name:dict(zip(('bytes','chain'),chain(name))) for name in entries if name.startswith(('user::','tool::fontpack::'))}
    return dict(elf_bytes=len(data),segments=segments,functions=functions,chains=public,
                method='exact frozen-backend prologue constants plus module-resolved direct call graph; no recursion; excludes external caller/kernel stack')
