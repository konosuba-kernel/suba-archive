"""Independent host-side wire fixtures; expected regions are explicit, not parsed back."""
import struct
from pathlib import Path

RAM = (0x80000000, 0x20000000)
ROOT_PROPS = [('#address-cells', struct.pack('>I', 2)), ('#size-cells', struct.pack('>I', 2))]
MEMORY = ('memory@80000000', [('device_type', b'memory\0'), ('reg', struct.pack('>QQ', *RAM))], [])


def node(name, properties=(), children=()):
    return name, list(properties), list(children)


def reserved(children=(), properties=None):
    return node('reserved-memory', ROOT_PROPS + [('ranges', b'')] if properties is None else properties, children)


def hole(name='hole@81000001', pairs=((0x81000001, 0x1234),), properties=(), children=()):
    return node(name, [('reg', b''.join(struct.pack('>QQ', *pair) for pair in pairs))] + list(properties), children)


def blob(children=None, properties=None, reservations=(), root_name=''):
    strings = bytearray()
    names = {}

    def word(value):
        return struct.pack('>I', value)

    def encode(item):
        name, props, child_nodes = item
        raw = name.encode() + b'\0'
        result = bytearray(word(1) + raw + bytes((-len(raw)) % 4))
        for key, value in props:
            if key not in names:
                names[key] = len(strings)
                strings.extend(key.encode() + b'\0')
            result.extend(word(3) + word(len(value)) + word(names[key]) + value + bytes((-len(value)) % 4))
        for child in child_nodes:
            result.extend(encode(child))
        return result + word(2)

    tree = encode(node(root_name, ROOT_PROPS if properties is None else properties,
                       [MEMORY] if children is None else children)) + word(9)
    reserve = b''.join(struct.pack('>QQ', *pair) for pair in reservations) + bytes(16)
    structure_offset = 40 + len(reserve)
    string_offset = structure_offset + len(tree)
    header = struct.pack('>10I', 0xd00dfeed, string_offset + len(strings), structure_offset,
                         string_offset, 40, 17, 16, 0, len(strings), len(tree))
    return header + reserve + tree + strings


def u32(raw, offset, value):
    result = bytearray(raw)
    struct.pack_into('>I', result, offset, value)
    return bytes(result)


def structure(raw):
    return struct.unpack_from('>I', raw, 8)[0]


def cases(fixtures):
    result = []

    def add(name, data, code=0, regions=(), oracle=False):
        result.append(dict(name=name, data=data, expected_exit=code, regions=list(regions), oracle=oracle))

    base = blob()
    add('minimal', base, oracle=True)
    add('qemu-virt', (fixtures/'qemu-virt.dtb').read_bytes(), oracle=True)
    add('opensbi-runtime', (fixtures/'opensbi-runtime.dtb').read_bytes(),
        regions=[(0x80000000, 0x40000), (0x80040000, 0x20000)], oracle=True)
    add('extra-storage-after-total', base + bytes(16))
    add('nop-before-root', u32(base[:structure(base)] + struct.pack('>I', 4) + base[structure(base):], 4, len(base)+4), 1)
    # Valid NOP: move string offset and update structure size as well as totalsize.
    nop = base[:structure(base)] + struct.pack('>I', 4) + base[structure(base):]
    nop = u32(u32(u32(nop, 4, len(nop)), 12, struct.unpack_from('>I', base, 12)[0]+4),
              36, struct.unpack_from('>I', base, 36)[0]+4)
    add('valid-nop-before-root', nop)  # DTSpec permits NOP; dtc 1.7 rejects this position.
    pair = (0x81000001, 0x1234)
    add('reservation-map', blob(reservations=[pair]), regions=[pair], oracle=True)
    add('reserved-static', blob(children=[MEMORY, reserved([hole()])]), regions=[pair], oracle=True)
    add('reserved-multiple-reg', blob(children=[MEMORY, reserved([hole(pairs=[pair, (0x82000000, 0x1000)])])]),
        regions=[pair, (0x82000000, 0x1000)], oracle=True)
    add('cross-source-overlap', blob(children=[MEMORY, reserved([hole()])], reservations=[pair]),
        regions=[pair, pair], oracle=True)
    add('no-map-preserved', blob(children=[MEMORY, reserved([hole(properties=[('no-map', b'')])])]),
        regions=[pair], oracle=True)
    add('reusable-preserved', blob(children=[MEMORY, reserved([hole(properties=[('reusable', b'')])])]),
        regions=[pair], oracle=True)
    for status in (b'ok\0', b'okay\0'):
        add('memory-status-'+status[:-1].decode(), blob(children=[node(MEMORY[0], MEMORY[1]+[('status', status)])]), oracle=True)
        add('reserved-status-'+status[:-1].decode(), blob(children=[MEMORY, reserved([hole(properties=[('status', status)])],
            ROOT_PROPS+[('ranges', b''), ('status', status)])]), regions=[pair], oracle=True)
    intervals = [(0x81000000+i*0x2000, 0x1000) for i in range(33)]
    add('capacity-exact-map', blob(reservations=intervals[:32]), regions=intervals[:32], oracle=True)
    add('capacity-exact-reg', blob(children=[MEMORY, reserved([hole(pairs=intervals[:32])])]), regions=intervals[:32], oracle=True)
    add('capacity-over-map', blob(reservations=intervals), 3)
    add('capacity-over-reg', blob(children=[MEMORY, reserved([hole(pairs=intervals)])]), 3)
    add('capacity-combined', blob(children=[MEMORY, reserved([hole(pairs=intervals[31:])])], reservations=intervals[:31]), 3)
    for count in range(len(base)):
        add(f'truncated-{count:03}', base[:count], 1)
    add('input-capacity-exact', base + bytes(65536-len(base)))
    add('input-limit', base + bytes(65537-len(base)), 3)
    for label, field, value, code in [
        ('magic',0,0,1), ('total-short',4,39,1), ('total-long',4,len(base)+1,1),
        ('version-old',20,16,2), ('version-new',20,18,2), ('last-compatible',24,17,2),
        ('reserve-header',16,32,1), ('reserve-unaligned',16,41,1), ('reserve-overflow',16,0xfffffff8,1),
        ('structure-unaligned',8,structure(base)+1,1), ('structure-overflow',8,0xfffffffc,1),
        ('strings-overlap',12,structure(base),1), ('strings-outside',12,len(base)+1,1),
        ('structure-length-overflow',36,0xfffffffc,1), ('strings-length-overflow',32,0xffffffff,1),
        ('structure-short',36,8,1), ('structure-length-unaligned',36,13,1),
    ]:
        add('header-'+label, u32(base,field,value),code)
    add('map-unterminated', base[:40]+struct.pack('>QQ', *pair)+base[56:],1)
    add('map-overlap', blob(reservations=[pair, pair]),1)
    for label, region in [('empty',(0x81000000,0)), ('below',(0x7fffffff,1)),
                          ('above',(0xa0000000,1)), ('cross-end',(0x9fffffff,2)),
                          ('overflow',(0xfffffffffffffff0,0x20))]:
        add('map-'+label,blob(reservations=[region]),1)
        add('reg-'+label,blob(children=[MEMORY,reserved([hole(pairs=[region])])]),1)
    add('missing-memory',blob(children=[]),2)
    add('duplicate-memory',blob(children=[MEMORY,MEMORY]),1)
    add('duplicate-reserved-parent',blob(children=[MEMORY,reserved(),reserved()]),1)
    add('duplicate-reserved-child',blob(children=[MEMORY,reserved([hole(),hole()])]),1)
    add('nonempty-root-name',blob(root_name='root'),1)
    add('nested-memory',blob(children=[MEMORY,node('soc',children=[MEMORY])]),2)
    add('memory-alias',blob(children=[node('ram@80000000',MEMORY[1])]),2)
    add('reserved-alias',blob(children=[MEMORY,node('reserved-memory@0',ROOT_PROPS+[('ranges',b'')])]),2)
    add('nested-reserved',blob(children=[MEMORY,node('soc',children=[reserved()])]),2)
    add('nested-reservation',blob(children=[MEMORY,reserved([hole(children=[node('subhole')])])]),2)
    add('memory-has-child',blob(children=[node(MEMORY[0],MEMORY[1],[node('child')])]),2)
    add('memory-wrong-type',blob(children=[node(MEMORY[0],[('device_type',b'ram\0'),MEMORY[1][1]])]),2)
    add('memory-wrong-range',blob(children=[node(MEMORY[0],[MEMORY[1][0],('reg',struct.pack('>QQ',0x80000000,0x10000000))])]),2)
    add('memory-multi-reg',blob(children=[node(MEMORY[0],[MEMORY[1][0],('reg',struct.pack('>QQQQ',*RAM,*RAM))])]),2)
    for missing in (0,1):
        add('memory-missing-'+str(missing),blob(children=[node(MEMORY[0],[MEMORY[1][1-missing]])]),2)
        add('root-missing-cell-'+str(missing),blob(properties=[ROOT_PROPS[1-missing]]),2)
    for field in ROOT_PROPS:
        add('root-duplicate-'+field[0],blob(properties=ROOT_PROPS+[field]),1)
        add('reserved-duplicate-'+field[0],blob(children=[MEMORY,reserved(properties=ROOT_PROPS+[('ranges',b''),field])]),1)
    for field in MEMORY[1]+[('status',b'ok\0')]:
        props = MEMORY[1]+[field] if field[0]!='status' else MEMORY[1]+[field,field]
        add('memory-duplicate-'+field[0],blob(children=[node(MEMORY[0],props)]),1)
    for field in [('reg',struct.pack('>QQ',*pair)),('status',b'ok\0'),('no-map',b''),('reusable',b'')]:
        props = [field] if field[0]=='reg' else [field,field]
        add('reservation-duplicate-'+field[0],blob(children=[MEMORY,reserved([hole(properties=props)])]),1)
    add('reserved-duplicate-ranges',blob(children=[MEMORY,reserved(properties=ROOT_PROPS+[('ranges',b''),('ranges',b'')])]),1)
    add('reserved-no-ranges',blob(children=[MEMORY,reserved(properties=ROOT_PROPS)]),2)
    add('reserved-translated',blob(children=[MEMORY,reserved(properties=ROOT_PROPS+[('ranges',bytes(24))])]),2)
    for name,value in [('size',struct.pack('>Q',4096)),('alloc-ranges',struct.pack('>QQ',*pair)),
                       ('alignment',struct.pack('>Q',4096)),('ranges',b'')]:
        add('reservation-unsupported-'+name,blob(children=[MEMORY,reserved([hole(properties=[(name,value)])])]),2)
    add('reservation-no-reg',blob(children=[MEMORY,reserved([node('dynamic',[('size',struct.pack('>Q',4096))])])]),2)
    add('reservation-empty-reg',blob(children=[MEMORY,reserved([hole(pairs=[])])]),1)
    add('reservation-short-reg',blob(children=[MEMORY,reserved([node('short',[('reg',bytes(15))])])]),1)
    add('contradictory-reservation-flags',blob(children=[MEMORY,reserved([hole(properties=[('no-map',b''),('reusable',b'')])])]),1)
    add('nonempty-no-map',blob(children=[MEMORY,reserved([hole(properties=[('no-map',b'bad')])])]),1)
    for value in (b'disabled\0',b'okay',b'',b'okay\0bad'):
        label=value.hex() or 'empty'
        add('memory-status-bad-'+label,blob(children=[node(MEMORY[0],MEMORY[1]+[('status',value)])]),2)
        add('reservation-status-bad-'+label,blob(children=[MEMORY,reserved([hole(properties=[('status',value)])])]),2)
        add('reserved-status-bad-'+label,blob(children=[MEMORY,reserved(properties=ROOT_PROPS+[('ranges',b''),('status',value)])]),2)
    add('usable-memory',blob(children=[node(MEMORY[0],MEMORY[1]+[('linux,usable-memory',struct.pack('>QQ',*RAM))])]),2)
    add('chosen-usable-range',blob(children=[MEMORY,node('chosen',[('linux,usable-memory-range',struct.pack('>QQ',*RAM))])]),2)
    add('wrong-root-cells',blob(properties=[('#address-cells',struct.pack('>I',1)),ROOT_PROPS[1]]),2)
    add('short-root-cells',blob(properties=[('#address-cells',bytes(3)),ROOT_PROPS[1]]),1)
    add('unknown-device-reg-ignored',blob(children=[MEMORY,node('device@deadbeef',[('reg',bytes(7))])]),oracle=True)
    add('bad-node-character',blob(children=[MEMORY,node('bad/name')]),1)
    add('empty-nonroot-node',blob(children=[MEMORY,node('')]),1)
    for levels,expected in [(31,0),(32,3)]:
        nested=node('leaf')
        for index in range(levels-1): nested=node('branch'+str(index),children=[nested])
        add('depth-'+str(levels+1),blob(children=[MEMORY,nested]),expected)
    for children_count,expected in [(510,0),(511,3)]:
        add('nodes-'+str(children_count+2),blob(children=[MEMORY]+[node('device'+str(i)) for i in range(children_count)]),expected)
    # Mutation of unambiguous token offsets in the minimal tree.
    start=structure(base)
    add('unknown-token',u32(base,start,99),1)
    add('end-before-root',u32(base,start,9),1)
    add('extra-end-node',u32(base,start,2),1)
    add('root-name-unterminated',base[:start+4]+b'x'*(len(base)-start-4),1)
    property_start=start+8
    add('property-length-overflow',u32(base,property_start+4,0xffffffff),1)
    add('property-nameoff-outside',u32(base,property_start+8,0xffffffff),1)
    strings_start=struct.unpack_from('>I',base,12)[0]
    add('property-name-unterminated',base[:strings_start]+b'x'*(len(base)-strings_start),1)
    add('property-name-empty',u32(base,property_start+8,len('#address-cells')),1)
    add('node-padding-nonzero',base[:start+5]+b'x'+base[start+6:])
    memory_type=base.index(b'memory\0')
    add('property-padding-nonzero',base[:memory_type+7]+b'x'+base[memory_type+8:])
    tree_end=start+struct.unpack_from('>I',base,36)[0]
    add('missing-final-end',u32(base,tree_end-4,4),1)
    add('missing-root-close',u32(base,tree_end-8,4),1)
    add('end-with-open-depth',u32(base,tree_end-8,9),1)
    # Move a valid root property after the child; wire lengths are unchanged.
    root_prop=base[property_start:property_start+16]
    late=base[:property_start]+base[property_start+16:tree_end-8]+root_prop+base[tree_end-8:]
    add('property-after-child',late,1)
    add('memory-empty-unit-address',blob(children=[node('memory@',MEMORY[1])]),1)
    add('node-double-unit-address',blob(children=[MEMORY,node('device@0@1')]),1)
    add('property-name-length-31',blob(properties=ROOT_PROPS+[('x'*31,b'')]))
    add('property-name-too-long',blob(properties=ROOT_PROPS+[('x'*32,b'')]),1)
    add('property-name-bad-character',blob(properties=ROOT_PROPS+[('bad/name',b'')]),1)
    add('reserved-device-memory-alias',blob(children=[MEMORY,reserved([hole(properties=[('device_type',b'memory\0')])])]),2)
    add('bare-memory-name',blob(children=[node('memory',MEMORY[1])]),oracle=True)
    add('map-adjacent',blob(reservations=[(0x81000000,1),(0x81000001,1)]),
        regions=[(0x81000000,1),(0x81000001,1)],oracle=True)
    for count, expected in [(32,0),(33,3)]:
        entries=[(0x81000000+i*4096,4096) for i in range(count)]
        add('reserved-names-'+str(count),blob(children=[MEMORY,reserved([
            hole(name='hole@'+format(region[0],'x'),pairs=[region]) for region in entries])]),
            expected, regions=entries if expected==0 else ())
    return result
