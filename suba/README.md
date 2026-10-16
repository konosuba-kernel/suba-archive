# suba

konOSuba 的新内核与系统环境：主要使用 S-next 和少量汇编，运行于固定的 QEMU RISC-V 64 虚拟机器。

目标是整体设计并构建一个可理解的系统：隔离的多进程、持久文件存储、可重叠窗口桌面、支持 UTF-8 和中文字形的编辑环境，以及能够在系统内重建编译器、内核和必要汇编部分的工具链。

## 当前状态

2026-10-16：K0、K2–K8 已独立验收。K7 修复空/迟到块设备通知被误判为故障的问题；K8 已在 suba 内完成 C0→C1→C2→C3 全文件固定点、源码行为扰动及同输入 Linux 对照。原始偶发 panic70 与旧 DMA 第61轮失败仍保留为未归类历史样本，不倒推为同一根因。见 [K7 独立验收](docs/workflows/through-k7/K7-acceptance-r3.md)、[K8 独立验收](docs/workflows/through-k10/K8-acceptance-r2.md)与[推进至 K10](docs/workflows/through-k10/DELIVERY.md)。

当前工作环境入口是 [构建运行说明](docs/K7_RUN.md)：`tools/build_system.py` 创建一次性初始环境，`tools/run_system.py` 重复使用持久盘。只有可信desktop从RAM引导；编译器、编辑器、构建工具及生成应用均由guest文件系统加载。编辑、保存、冻结、诊断和发布使用真实内核服务，没有宿主文件代理。性能结果及失败修正见[工程记录](docs/workflows/through-k7/K7-engineering-notes.md)；旧K5运行夹具的复现应使用其冻结版本。

- [范围修订](design/SCOPE_REVISION.md)：保留原生编译器固定点与内核/S0构建，允许宿主按字节搬运部署，磁盘更新链延期。
- [整体架构](design/ARCHITECTURE.md)：系统边界、部署、状态归属、自举链和成本。
- [核心合同](design/CONTRACTS.md)：地址空间、入口、等待、回收、存储与窗口生命周期。
- [实施计划](design/IMPLEMENTATION.md)：依赖 DAG、分阶段探针及整体验收。
- [代码与风格规约](CODE_STYLE.md)：模块、控制流、错误、unsafe、资源生命周期与审查标准；[规约验收记录](design/STYLE_DELIVERY.md)。

首版选择小型模块化宏内核、隔离进程、独立可信桌面，以及普通编辑器/编译器；固定 QEMU RV64 单核、512 MiB RAM、ramfb 软件图形。原生应用构建与完整系统自举分阶段验收；K8编译器固定点已完成；K9内核/S0原生构建与K10整体验收正在推进。首版经固定 RAM 启动链验证 guest 构建的 kernel ELF；系统内安装、切换和回退内核移出首版门槛。普通文件持久化及正常 flush/关机要求不变。

`SOS/` 已弃用，其需求、宿主化路线和实现选择不作为 suba 的约束。原 K0 实施基线为相邻 `biomiya/` 仓库的提交 `a86586e`；目录迁移后的当前编译器位于 `biomiya/compiler/`，工具和回归分别位于 `biomiya/tools/`、`biomiya/tests/`，具体见[迁移说明](../biomiya/docs/layout-migration.md)。当前K0编译器由工作树内容哈希识别，参见 [S-next 使用参考](../biomiya/docs/reference/s-next-0.1.md)与[编译器交付记录](docs/workflows/k0/DELIVERY.md)。编译器已有 Linux-user 自举证据，suba 内的编译器自举已有本轮 K8 独立证据。

架构清晰是硬要求，没有预设的代码行数上限。内核、驱动、文件系统、桌面、编辑器、用户库和系统内构建工具均记录实际成本；编译器、测试、外部基础设施和字体数据分别列账。
