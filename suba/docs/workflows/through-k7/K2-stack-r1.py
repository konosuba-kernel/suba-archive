#!/usr/bin/env python3
"""Reviewer stack audit on an already built K2 image; includes direct VT call chains."""
import importlib.util,json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[3];folder=Path(sys.argv[1]).resolve()
spec=importlib.util.spec_from_file_location('cost',root/'tests/k6/cost.py');cost=importlib.util.module_from_spec(spec);spec.loader.exec_module(cost)
sources=[line.split()[1] for line in (folder/'kernel/kernel.build').read_text().splitlines() if line.startswith('source ')]
record=cost.measure(folder/'build/kernel.elf',folder,sources)
entries={f['name']:f for f in record['functions']}
def chain(name,seen=()):
    if name in seen:raise RuntimeError('recursive kernel call graph')
    size,path=max((chain(c,seen+(name,)) for c in entries[name]['calls']),default=(0,[]))
    return size+entries[name]['frame_bytes'],[name]+path
record['kernel_chains']={name:chain(name) for name in ['kernel::entry::start','kernel::entry::dispatch','kernel::entry::panic']}
record['method']+='; independent kernel roots; S0 wrappers use no stack; bridge overhead must be added separately'
(folder/'cost-review.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record['kernel_chains']))
