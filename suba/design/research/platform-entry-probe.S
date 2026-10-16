/* Host-assembled entry/reset feasibility probe; not a suba bootloader. */
.section .text
.globl _start
_start:
    li t0, 0x10000000
    li t1, 'S'
    sb t1, 0(t0)
    li t2, 0x88000000
    ld t3, 0(t2)
    bnez t3, second
    li t3, 1
    sd t3, 0(t2)
    li t1, '0'
    sb t1, 0(t0)
    li t1, 10
    sb t1, 0(t0)
    li a7, 0x53525354
    li a6, 0
    li a0, 1
    li a1, 0
    ecall
    j failed
second:
    li t1, '1'
    sb t1, 0(t0)
    li t1, 10
    sb t1, 0(t0)
    li a7, 0x53525354
    li a6, 0
    li a0, 0
    li a1, 0
    ecall
failed:
    li t0, 0x10000000
    li t1, 'F'
    sb t1, 0(t0)
1:  wfi
    j 1b
