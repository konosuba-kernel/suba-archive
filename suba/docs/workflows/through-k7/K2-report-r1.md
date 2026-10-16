# K2-r1 实施报告（待独立验收）

作者 `/root/memory_resume`，独立验收者 `/root`。继承已验收 K2a/K2b，未改历史冻结记录；本轮交付完整剩余 K2，不自行提交。候选/输入身份见 `K2-candidate-r1.json`，原始验证结果身份见 `K2-evidence-r1.json`。所有实施、测试和工具均使用当前 S-next E3；未修改编译器或使用宿主链接器/汇编器修补正式 ELF。

## 实际实现

- `space` 独占 Sv39 页表与页归属账本；ASID=0，切换后 sfence.vma。内核同址映射 RX/R/RW+NX，固件 0x80000000–0x80200000 不映射。用户根的低 1 GiB 私有；共享内核分支不带 U。UART/fw_cfg 仅两页映射到 physical+0x40000000，PLIC/virtio 留给 K4。
- `elf` 纯解析 RV64 静态 ET_EXEC，最多 8 个排序、不重叠、4 KiB 对齐的 PT_LOAD；仅 R/RX/RW，禁止 RWX、错误 ABI、非初始化可执行入口、溢出和越窗。total 上限 64 MiB，BSS 的零字节读取请求不计算多余文件偏移。
- `loader` 以 Job/Need/Step 推进同一生产装载路径：每次最多 4096 文件字节、一个用户页及最多两个页表页；BSS 和未写部分来自 allocator 整页清零。提供 1 MiB RW+NX 用户栈、下方 guard、RO 启动参数页（当前 argc=0）。初始 RAM provider 只负责给该 loader 提供文件片；K4 文件 provider 继续用它。
- `process` 独占 16 个 slot+generation 身份、保存现场和生命周期；Loading→Ready→Running/Blocked→Dying→Exited→collect。代数耗尽不复用，旧身份拒绝。应用异常只终止当前进程，未知中断先返回 Invalid，由可信顶层 panic，不能 overflow 或误杀应用。
- S0 保存 x1–x31、sepc/sstatus/scause/stval；进入共享 128 KiB 内核栈，返回清除 SPP/SUM/MXR/FS/VS，仅设置 SPIE。用户 x27、x28 和无效用户 sp 均能跨 trap 保留。内核栈 guard 和独立 panic 页已映射；紧急输出本身不使用受损栈。
- SBI TIME + QEMU 10 MHz timebase，10 ms 抢占时间片、round-robin。进程退出/装载失败统一每步最多回收 16 页；只有完整回收后 collect 才允许槽复用。当前 K2 顶层只分派 exit，其余调用返回 UNSUPPORTED；初始测试进程全部退出后核对 free 基线并停机。K3 接常驻 idle、完整 syscall/资源清理。

## 新的可信启动前提

BootInfo v1 原样保留；另增 `abi/ram_start.vt` 定义 256 B v1 记录，地址 0x803f0000，不借用 BootInfo 保留字节。宿主检查 boot 实际 ELF/BSS/栈/DTB 最高地址低于该记录；kernel 原 ELF 同一文件路径一份正常 ELF 装载、一份原字节装到 0x88000000，SHA 身份核对且不重打包。用户 fixture 原字节位于后续高 RAM；所有源完整范围经 BootInfo reservation 登记，读源前验证普通 RAM、长度、溢出、排序/重叠、容量和保留覆盖。

内核原 ELF 是准确 RX/R/RW 边界的可信来源；记录与其副本均为启动器可信输入，不宣称能在恶意启动器下建立安全性。未来初始用户映像改从 FS 来，权限仍由同一 ELF decoder/loader 判定。固定 QEMU 512 MiB、单 hart、OpenSBI 是当前平台；未宣称 Linux ABI 兼容或磁盘 stage0 已实现。

旧 K0/K2b 注入工具按旧单阶段入口编写。本阶段当前启动回归入口是 `tools/check_k2.py`：basic 验实际 handoff；bad-boot-info 验拒绝；s-* 验可信异常。旧 `check_kernel_entry.py` / `check_ram_boot.py` 不再是当前整内核执行命令，也未声称其旧入口已重跑成功；旧冻结验收仍保留，纯页池实现未改。复现分类见 `tests/k2/README.md`。

## 验证与反例

全部真实 QEMU v11.1.1。最终生产 basic ELF SHA256 `76d0452c54b9d3542eb5f0e5e94dfd9a1e63bc7fada1550abf4b50ed30c3de7c`。最终说明性注释/空行变化与该二进制无关；冻结 basic 与前一 basic 字节相同。

| 验证 | 结果 |
|---|---|
| 两个同 VA 程序、8193 B BSS、初始化数据、正常 exit | 两者状态 0，所有私有页归还 |
| 两个纯死循环，各 x1–x31/四 CSR，两次真实定时陷入 | 两者现场准确且可恢复；含 x27/x28、非法用户 sp |
| U null、S-mode CSR、栈 guard、写 RX、写 R、执行 RW、读 kernel | 硬件 cause 13/2/13/15/15/12/13；另一程序存活，全回收 |
| S 固件区读、text 写、内核栈 guard 读 | cause 13/15/13 + 准确 stval，可信停机 |
| 32 次部分创建失败 + stale 身份 + 未缩小的 24576 页配额 | 每次回到 free 基线；真实约 96 MiB 配额耗尽并完整回收 |
| NoMemory loader 失败 | 测试副本配额=3；两次状态 7、回收正确，明确不是生产容量 |
| 实际 RWX 用户 ELF | 拒绝该映像，另一程序正常退出 |
| 37 个实际 decoder 边界案例 | 正例接受；近 usize::MAX 等畸形输入拒绝 |
| x28 恢复删除负控 | 测试副本准确 panic 80；正例通过 |
| 未支持高位中断注入 | 测试副本准确 panic 10，无应用故障回收标记 |
| 坏 BootInfo/启动描述符 | 分别 panic 1 / 8 |

保留早期失败：`build/k2-compile-1..4` 的语言语法不匹配；`k2-run-1` 的宿主元数据键错误；`k2-registers-1` 发现 S0 伪 branch/jump 使用 x31，原探针自身破坏 x31，改为真实 jalr 自循环后验证。没有删除失败证据或把测试副本当生产实现。

## 实际成本和后续边界

最终 production 编译：16 个 VT 源、2 个 S0，text 340908 B，ELF 352272 B，最大单函数栈帧 9344 B；PT_LOAD 内存跨度 6797040 B，BSS 6448864 B（约 6.15 MiB）。这是单帧测量，不声称已证明整个最深调用链栈界或达到 K7 的 5 ms/99% 延迟目标。

`check_k2_cost.py` 在明确标记测试副本中用实际编译器 sizeof 私有类型：Owned=12 B、space Record=32 B、process Record=736 B、Frame=8 B。因此 16×24576 的页账本恰为 **4718592 B（4.5 MiB）**；另有 12288 B 内核页句柄表、512 B space 表、11776 B process 表。既有 allocator 131072×12 B=1.5 MiB 元数据照计，未优化容量。运行期另付实际页表及 32 页共享栈/1 页 panic 栈，用户 256 页栈及参数页均纳入每进程 24576 页配额。

公共页归属账本当前只支持追加和整空间 reap；K3 动态 free 必须做逐页 unmap、sfence 与空槽复用，不能在 append-only count 上反复消耗配额。map_user 只是受信映射原语；用户动态区间/请求权限由 K3 调用边界收紧。没有用户 DMA、句柄、FS、设备 IRQ、桌面或原生编译器执行的完成声明。

设计读写路径的大小和分片上界可在叶模块核对；编解码和权限检查无 I/O，持状态模块为唯一所有者。语言只支持单载荷枚举且无 enum equality，局部 `state_code` 仅用于私有状态比较；嵌套 match 是语言表达限制，未引入通用调度/异步框架。此轮优先保存可审计生命周期，未以缩减行数隐藏容量成本。

机器规则依据：[RISC-V Supervisor ISA](https://docs.riscv.org/reference/isa/v20260120/priv/supervisor.html)、[SBI TIME 原文](https://raw.githubusercontent.com/riscv-non-isa/riscv-sbi-doc/master/src/ext-time.adoc)。10 MHz 亦由当前 QEMU DTB 的 `timebase-frequency=0x989680` 核对。
