"""Host oracle uses Python Unicode strings, never the production gap-buffer algorithm."""
import bisect
import struct

MAX_BYTES = 4194304

def boundaries(text):
    result = [0]
    for character in text:
        result.append(result[-1]+len(character.encode()))
    return result


class Model:
    def __init__(self, capacity, initial):
        self.capacity = capacity
        self.text = initial.decode('utf8')
        self.cursor = self.anchor = len(initial)
        self.version = 0

    def frame(self, code=0):
        raw = self.text.encode()
        return struct.pack('<5I', code,self.version,self.cursor,self.anchor,len(raw))+raw

    def apply(self, action):
        tag,*args=action
        points=boundaries(self.text)
        index=points.index(self.cursor)
        if tag==1:
            anchor,cursor=args
            if anchor not in points or cursor not in points:return 2
            self.anchor,self.cursor=anchor,cursor
        elif tag==2:
            data=args[0]
            left,right=sorted((self.cursor,self.anchor))
            kept=points[-1]-(right-left)
            if len(data)>MAX_BYTES-kept:return 3
            if len(data)>self.capacity-kept:return 4
            try: replacement=data.decode('utf8')
            except UnicodeDecodeError:return 1
            self.text=self.text[:points.index(left)]+replacement+self.text[points.index(right):]
            self.cursor=self.anchor=left+len(data)
            self.version+=1
        elif tag==3:
            motion,extend=args
            position=self.cursor
            if motion==0:
                position=points[max(0,index-1)]
                if not extend and self.cursor!=self.anchor:position=min(self.cursor,self.anchor)
            elif motion==1:
                position=points[min(len(self.text),index+1)]
                if not extend and self.cursor!=self.anchor:position=max(self.cursor,self.anchor)
            elif motion==2:
                position=len(self.text[:index].rsplit('\n',1)[0].encode())+1 if '\n' in self.text[:index] else 0
            elif motion==3:
                suffix=self.text[index:]
                position=self.cursor+len(suffix.split('\n',1)[0].encode())
            elif motion==4:position=0
            elif motion==5:position=points[-1]
            self.cursor=position
            if not extend:self.anchor=position
        elif tag==4:
            backward=args[0]
            if self.cursor==self.anchor:
                other=points[max(0,index-1)] if backward else points[min(len(self.text),index+1)]
                if other==self.cursor:return 0
                self.anchor=other
            return self.apply((2,b''))
        elif tag==5:
            down,extend=args
            prefix=self.text[:index]
            row=prefix.count('\n')
            column=len(prefix.rsplit('\n',1)[-1])
            lines=self.text.split('\n')
            target=row+1 if down else row-1
            if target<0 or target>=len(lines):return 0
            before='\n'.join(lines[:target])
            offset=len(before.encode())+(1 if target else 0)
            self.cursor=offset+len(lines[target][:column].encode())
            if not extend:self.anchor=self.cursor
        return 0


def encode_action(action):
    tag,*args=action
    if tag==1:return b'\1'+struct.pack('<II',*args)
    if tag==2:return b'\2'+struct.pack('<I',len(args[0]))+args[0]
    return bytes([tag,*args])


def editor_case(capacity, initial, actions):
    data=struct.pack('<II',capacity,len(initial))+initial+b''.join(encode_action(a) for a in actions)
    if len(initial)>MAX_BYTES:return data,struct.pack('<I',3)
    if len(initial)>capacity:return data,struct.pack('<I',4)
    try:model=Model(capacity,initial)
    except UnicodeDecodeError:return data,struct.pack('<I',1)
    output=model.frame()
    for action in actions:output+=model.frame(model.apply(action))
    return data,output
