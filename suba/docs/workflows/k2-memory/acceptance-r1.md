# K2a I-r1 最终独立验收：通过

验收者 `/root/k2_acceptance`，2026-10-15。未参与 R、M、I 的设计实现或测试编写；此前只做只读预审，正式验收以冻结 I-r1 为准。

候选 `I-candidate-r1.json` SHA256 `5c518febd5bdeacdca9a7d6326caa3a41f7c5090a22f5d80e7a08c06ba752ed0`。R-r1、M-r1 依赖均已有 root 独立接受。再次逐项核验 R 的 9 项、M 的 15 项、I 的 28 项文件/依赖/编译器身份，全部匹配。这里的项数包含依赖，不是生产文件数。

判定覆盖当前 R→M→I 组合：首版范围修订、有限捐赠物理页所有权，以及真实 S-mode 内核启动接入。未发现未处理的阻断问题，I-r1 满足本轮合同。完整 K2、K3、系统内编译仍未完成。

## 独立执行与反例

从 `suba/` 执行以下命令，均使用冻结 E3 `049c6e094ccd044fba3b5d357583013b77f0e8e9a98d431ad919e02b0cda2144`：

- `python3 tools/check_memory.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/k2-acceptance-component-r1`：8/8。初始化拒绝后重试、成功后禁止重置、耗尽、非头部释放、旧身份拒绝、其他页不被改写、缩限代数退役、清零/代数错误副本及成本探针通过。
- `python3 tools/check_memory_boot.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/k2-acceptance-memory-r1`：2/2。真实内核池分配 64 页并逐页检查唯一性/对齐/全页零，写脏后全部释放，再取一个实际旧地址检查全页清零与失效身份拒绝；移除清零副本实际产生 panic 24。
- `python3 tools/check_kernel_entry.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/k2-acceptance-entry-r1`：4/4。正常交接、错误 magic、真实 illegal instruction 以及成功标记之后发生异常的负控被正确分类。
- `python3 build/k2-acceptance-negative-r1.py`：验收者独立新增两项真实 QEMU 负控。仅清 511/512 个字的副本在回收后再分配时实际 panic 24；将每次代数固定为 1 的副本在旧身份检查时实际 panic 26。两者都没有输出 memory verified 或 handoff accepted。脚本与完整命令、日志一起保存于验收证据，未修改冻结源码。

证据：[acceptance-evidence-r1.json](acceptance-evidence-r1.json)，SHA256 `bf298724cde350dceadab49d856d556561ecada6c4fa474e19a052457a46fef0`。含完整独立运行记录和负控脚本。首次哈希检查脚本误把 M 嵌套依赖当作平面映射，立即失败；修正读取结构后重新核验全部项，失败尝试不被当作通过证据。

观察器必须见到完整预期记录、符合事件顺序、在有限 500 ms 窗口内继续存活且无禁止记录。没有把超时、打印一个成功前缀或退出当成通过；也没有把有限观察夸称为永久停机证明。

## 代码与组合合同

捐赠者的专用 STORAGE 长度为 64×4096+4095，对齐 skip 在 0..4095，因此捐赠的 64 页完整位于专用对象内。成功转交后没有公开切片或其他模块访问入口。核对编译器 `image.vt` 的静态对象布局：每个对象从当前区域末端对齐放置并推进末端；`rv64.vt` 为启动栈创建独立 BSS 对象。STORAGE、SLOTS、状态和启动栈互不重叠。内核的 RW 段始终包含这些对象；不依赖未验证的 RAM 空闲区推断。

初始化所有可拒绝检查在状态修改前完成。槽表容量 131072，索引转换可表示；初始化循环有容量上界。分配只摘空闲链头并清 512 字；释放、身份查询和统计为常数元数据工作。仅未分配且未退役的槽在空闲链，最终代数在释放时永久退役，因而分配递增不会回绕。失败身份不会改计数或链；free+allocated+retired=capacity 的更新点集中在所有者中。

Frame 字段私有但可复制，address 返回值不延长寿命或自动撤销裸指针。释放前终止所有借用、用户映射和 DMA，以及单执行上下文串行化，明确是 unsafe 调用者责任。当前启动实际关闭中断且没有其他消费者；尚未提供可被调度/IRQ 任意重入的分配器。

启动接入在窄 BootInfo 与 SIE 验证之后，失败进入可信 panic；生产镜像只初始化池，不执行测试循环。完整 FDT/保留区接管的旧 K1 注释已经归后续 K2，不再让延期磁盘启动阻塞此工作。

## 规模与范围

独立重算所有成本分组文件行数、字节和哈希，并从本次重建 ELF 解析 PT_LOAD；与 I-cost-r1 全部一致。正式 ELF SHA256 `17a175778742940534a48a87dd0be701850ada8c291ee249fbb990d29f022f36`，32772 B；probe ELF SHA256 `a4bdce3deb44b56c87a2bdf3a686118b4201325faae8a0f7770574ac57c8d10b`，49156 B。两种身份单独保留。

生产 kernel 352 行 VT + 111 行 S0，共享 ABI 199 行单列。固定元数据 1572864 B、池 backing 266239 B、栈 131072 B 均计入 RW 1970240 B，没有用 64 页开放容量掩盖 1.5 MiB 元数据成本。最大单函数 frame 不被当作整条调用链栈深。元数据容量策略是后续优化点，不是本轮正确性阻断。

范围修订在 REQUIREMENTS、ARCHITECTURE、CONTRACTS、IMPLEMENTATION 中一致：首版保留 guest 应用编译、编译器固定点、kernel/S0 完整 ELF 原生构建与持久保存；宿主仅搬运部署，guest/副本/装载身份必须一致，宿主同输入编译仅作 oracle。K1 磁盘选槽/更新延期，K4 明确独占存储传输且不等待 K1；普通文件正常 sync/FLUSH/重启读取、隔离回收和桌面要求未削弱。历史候选按原字节保留，不冒充新规范验收。

本次不证明全 RAM 接管、Sv39、普通 trap、定时抢占、用户隔离、完整进程回收、文件系统或系统内自举。编译器生产未修改，无需机械重复完整自举。后续 K2/K3 仍需各自验收。
