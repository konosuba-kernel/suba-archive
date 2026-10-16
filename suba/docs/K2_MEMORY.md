# K2a：引导页池与物理页所有权

2026-10-15。当前完成到 K2a；完整 K2 的 Sv39、普通 trap 和抢占尚未实现。首版范围按[目标修订 0.2](../design/SCOPE_REVISION.md)：应用与编译器原生构建、系统内生成完整内核 ELF 保留，安装/切换与磁盘 stage0 延后，宿主仅搬运生成的 ELF。

## 当前启动路径

固定 QEMU virt / RV64 / 单 hart / 512 MiB RAM，继续使用 [K0](K0.md) 的 RAM 启动链。编译器生成的入口先清 BSS、建立 128 KiB 栈，进入 `kernel::entry::start`；验证窄 BootInfo、确认 SIE 关闭后，由 `kernel::bootstrap_memory` 将专用 BSS 数组中的 64 个对齐页捐给 `kernel::memory`，最后输出交接标记并停机。正式镜像没有测试循环。

捐赠数组大小为 `64×4096+4095` 字节，对齐最多丢弃 4095 字节，所以 64 页必然完整位于该数组内。它是独立静态对象，与分配器元数据、入口栈和其他内核数据分开；成功捐赠后该模块不再访问数组。只允许启动期调用一次。分配器不会根据未完全验证的 BootInfo/FDT 把其余 RAM 当作空闲页。

## 模块和接口

|文件|责任|
|---|---|
|`kernel/memory.vt`|一个独占 extent、私有空闲链和代数表；校验页身份，分配清零、释放与退役|
|`kernel/bootstrap_memory.vt`|专用 BSS 页池的唯一捐赠者；不暴露存储视图|
|`kernel/entry.vt`|启动顺序、错误转 panic；不拥有分配器表|
|`tests/k2/memory_probe.vt`|仅测试镜像调用，真实读写内核页池并验证回收|

`initialize` 接收独占、长期有效、可写普通 RAM 的整页切片；拒绝不对齐、空、非整页、地址加法溢出和容量超限。失败不修改状态，成功后不能重置。可访问性、独占性与保留区排除由 unsafe 调用者证明，数字范围检查不能代替这些证明。

`allocate` 返回 `Ready(Frame)`、`Exhausted` 或 `NotReady`。空闲链摘头 O(1)，分配前清零整页（512 个字写入）。`release`、`address`、`stats` 元数据工作 O(1)，不等待。初始化最多处理 131072 项，属于引导期操作。

Frame 的槽和代数字段私有，但值可复制。重复和旧代数身份被拒绝；代数达到 u32 上限后释放的页永久退役，不回绕。Frame 不是语言线性类型，返回的裸地址也不会自动撤销；释放前调用者必须结束所有页访问、映射和 DMA。所有操作要求串行、不重入；将来启用 IRQ/调度前必须落实这一调用合同。

## 验证

从 `suba/` 执行，`--out` 必须是新的目录：

```sh
python3 tools/check_memory.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/memory-check
python3 tools/check_kernel_entry.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/entry-check
python3 tools/check_memory_boot.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/memory-boot-check
```

组件验证含初始化拒绝后重试、穷尽、非头部页回收、其他页内容不变、重复/失效身份、缩限代数退役，以及移除清零/代数递增的负控。缩限只改明确标识的测试副本，生产无测试开关。另有独立验收副本只清 511/512 个字，确认漏清末字可被检测。

真实 QEMU 测试分配全部 64 页，检查地址唯一/对齐/清零，写脏、释放，再分配检查全页清零和旧身份拒绝。移除清零的副本必须 panic 24，不能输出成功标记。保留 K0 的有效交接、坏 magic、可信异常和“成功标记后再异常”四个场景。停机观察为有限稳定窗口，不声称证明无限时间停机。

当前证据与独立判定见[交付记录](workflows/k2-memory/DELIVERY.md)。测试版插入的 probe 与正式版分别记录 ELF 身份；测试通过不能把 probe ELF 冒充正式产物。

## 成本与下一步

当前整个 `kernel/` 手写生产代码为 352 行 VT + 111 行 S0；共享 ABI 199 行单列。K2 测试 478 行，新增验证工具 239 行；共用 K0 观察器 187 行。行数包含空行/注释，编译器、K0 fixture 和历史测试不计入内核生产数，亦未被当作不存在。

正式内核 ELF 32772 B，RX 22780 B，RW 内存 1970240 B。其中元数据固定预留 131072×12=1572864 B（1.5 MiB），专用页池 backing 266239 B，入口栈 131072 B，其余为状态和布局对齐。当前仅开放 256 KiB 页池仍承担全部元数据成本，这是后续容量策略的明确优化点。生产最大单函数栈帧 1376 B，QEMU probe 为 3872 B；都不等于整条调用链最大栈深。

后续 K2 顺序：验证平台/FDT 与保留区并接管可用 RAM；实现 Sv39 页表和权限；完善 trap 现场与返回；再接定时器抢占和 K3 进程生命周期。当前没有用户隔离、应用终止回收或系统内编译能力，不能把本页的 Frame 生命周期视为进程机制已经完成。
