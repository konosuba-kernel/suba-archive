# I-r1 启动接入候选

作者 `/root`，2026-10-15。依赖已接受 R-r1、M-r1；独立最终验收 `/root/k2_acceptance`。

正式修改：新增 bootstrap_memory 捐赠者；entry 在交接验证和 SIE 检查后初始化页池；kernel.build 纳入两模块；K0 检查输入列表纳入新模块。修正入口旧注释，将完整 RAM/FDT 接管归后续 K2。未修改 ABI、机器层或编译器。原 K0 三个消费者的字节保存在 prior-k0-consumers，旧冻结记录仍只证明历史版本。

测试版修改：独立 memory_probe 插入启动末尾，同一生产 allocator/捐赠者实际处理 64 页；故意删清零的副本须 panic 24。测试退出码为定位检查失败的测试协议，不是生产错误接口。probe 按分配池/释放池/重用一页拆分；分配池的内层唯一性检查为有限 64 页测试，非运行期分配器扫描。

实测：

- `python3 tools/check_kernel_entry.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/k2-k0-regression-r1`：4/4，包含成功标记后的异常拒绝。
- `python3 tools/check_memory_boot.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/k2-integration-r1`：2/2，正常路径真实回收清零，漏清零副本实际 panic 24。
- M 独立复核 8/8 及 511 字清零负控见 M-acceptance-r1。

证据完整复制在 I-k0-verification-r1.json、I-memory-verification-r1.json；生产 ELF SHA256 `17a175778742940534a48a87dd0be701850ada8c291ee249fbb990d29f022f36`，probe ELF 身份单列，未覆盖生产。编译器仍为 layout-p4-r1/e3.elf，SHA256 `049c6e094ccd044fba3b5d357583013b77f0e8e9a98d431ad919e02b0cda2144`。没有编译器变更，不机械重跑完整自举。

独占范围证明：STORAGE 为专属静态对象；取模对齐 skip 位于 [0,4095]，STORAGE_BYTES=64*PAGE_BYTES+4095，捐赠全在该对象中。编译器 image.vt 对各静态对象依次对齐放置，入口栈也是独立 BSS 对象；memory 的 SLOTS/状态不与 STORAGE 共用。页池不会碰 kernel 镜像之外的 RAM，因此不依赖尚未完成的完整 FDT 接管。实际 QEMU 页循环补充此源码/布局证明。

规模和 ELF 段/最大单函数 frame 见 I-cost-r1.json；当前固定元数据约1.5MiB，无意隐藏为64页池成本。公开 Frame 仅检查身份；后续映射/DMA 回收和 IRQ 串行性仍需各使用者承担。

候选仅完成 K2a，无 Sv39、普通 trap、抢占、用户隔离、自举编译器或内核部署功能。README/设计仍为 R-r1 字节；当前实现进度集中 docs/K2_MEMORY.md。不自动提交。
