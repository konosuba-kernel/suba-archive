# K2 真实地址空间与进程验证

从 suba 根目录运行；每次使用新的输出目录，工具保留完整源码快照、编译命令、实际 ELF、QEMU 命令、串口日志和 verdict。编译器固定为已验收的 E3：

```sh
python3 tools/check_k2.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/my-k2-basic --case basic
python3 tools/check_k2.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/my-k2-registers --case registers
python3 tools/check_k2.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/my-k2-rollback --case rollback
python3 tools/check_k2_elf.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --elf build/my-k2-basic/build/user0.elf --out build/my-k2-elf
python3 tools/check_k2_cost.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/my-k2-cost
```

`--case` 的其他值：

| 类别 | 案例与判据 |
|---|---|
| U 异常 | `null`, `privileged`, `guard`, `text-write`, `ro-write`, `nx`, `kernel-read`：准确 scause，另一进程正常退出，全部私有页回收 |
| 可信 S 异常 | `s-firmware`, `s-text-write`, `s-guard`：准确 scause/stval，紧急停机；不能当应用异常处理 |
| 启动边界 | `bad-boot-info`, `bad-descriptor`：分别 panic 1/8 |
| 实际用户 ELF 拒绝 | `bad-user-elf`：有意破坏第一用户 ELF 的 flags，另一映像正常执行 |
| 生命周期 | `load-no-memory`：仅测试副本配额缩至 3，触发实际 loader NoMemory，收集状态 7，物理页无泄漏；正常 `rollback` 同时验证未缩小的 24576 页配额 |
| 现场负控 | `restore-negative`：仅测试副本删 x28 restore，必须 panic 80 |
| 可信中断边界 | `unknown-interrupt`：仅测试副本把保存的 cause 改成不支持的外部中断，必须 panic 10，无应用故障回收 |

`registers` 的两进程设置不同 x1–x30（含无效用户 sp），x31 保存循环 PC；两次真实 timer trap 对照全部寄存器和四个 CSR 后才终止。这验证保存及恢复，不依赖应用主动 yield。探针只读取生产 process 诊断接口。

`rollback` 在同一内核中重复 32 次部分装载失败，每次核对 free 页基线与失效身份，再真实消耗一次约 96 MiB 空间配额并回收。测试不另写 allocator/ELF loader。

旧 `check_kernel_entry.py` 的 K0 单次停机入口和 `check_ram_boot.py` 的注入锚点对应 K0/K2b 历史阶段，不再是当前完整内核启动入口。当前 handoff、坏 BootInfo 和可信异常分别由这里的 basic、bad-boot-info、s-* 验证；旧冻结证据不改。K2b 的 FDT 保留区/页池完整反例仍在原验收记录，本组不把它们冒称重跑。
