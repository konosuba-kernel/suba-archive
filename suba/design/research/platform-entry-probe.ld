OUTPUT_ARCH(riscv)
ENTRY(_start)
PHDRS { text PT_LOAD FLAGS(5); }
SECTIONS { . = 0x80200000; .text : { *(.text*) } :text }
