# I-r1 / A：独立组合验收

2026-10-15。判定：**通过**。实现作者 `/root`；验收者 `/root/ram_acceptance`，未参与 F/M/I 实现。本验收覆盖 I 实现与最终组合，不把本人先前 D 合同评审当作实现独立性证据。

候选 `I-candidate-r1.json` SHA256 `54340df9b0e9cfba40bd872fdde6c03a83a0e31497c27b8b7008c8020eccb2e4`。验收开始与结束均核对 files/inputs/dependencies 全部哈希、三项删除文件确实不存在。D-r3/F-r1/M-r2 与已有独立接受记录一致。没有改动生产源码、冻结候选或旧证据。

## 实际执行

工作目录 suba；全部使用候选指定的 `../biomiya/build/layout-p4-r1/e3.elf`。

- `python3 tools/check_ram_boot.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/k2-ram-a-qemu-r1`：6/6 通过；保留洞覆盖三种输入来源，漏 FDT 项与漏清零两个副本分别实际 panic26/panic24。
- `python3 tools/check_kernel_entry.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/k2-ram-a-k0-r1`：4/4 通过。最后一个先输出成功再触发非法指令，观察器确实拒绝，未将成功标记当作充分条件。
- `python3 tools/check_boot_info.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/k2-ram-a-info-r1`：543/543 通过；另逐行审查未逐字节枚举的保留零区、地址和容量边界。
- `python3 build/k2-ram-a-extra-r1/run.py`：3/3 通过，探针原文冻结为 acceptance-probe-r1.py。独立构造三个有区分力场景：仅漏 BootInfo 保留列表的副本实际 panic26；loader 传递原始地址 0xfffffffffffffff8 时受控 panic1、没有紧急异常；reservation map、reserved-memory 与 BootInfo 之间人为增加重叠，仍能穿越三个洞、容量保持六页扣减，未重复扣除重叠区。
- `python3 tools/measure_kernel.py build/k2-ram-k0-r1/valid/build/kernel.elf`：与 I-cost 全部源统计、段、62 个函数 frame、最大值和总和精确相符。独立新构建正式 ELF 与作者文件全字节身份相同：SHA256 `6ec17c0b69c14babf9bbfd16e05cdc0b6ea2d14e5ec024a646018a645c1003d1`。

执行命令、原始日志、预期/实际事件、输入与工具哈希见 acceptance-evidence-r1.json；543 用例的完整原始输入输出仍在其列出的 build 记录，报告保存其完整哈希。未机械重跑已独立接受的 F/M 组件，组合测试实际执行同一生产 F/M 源码。

## 源码与边界判定

BootInfo read 在构造切片前检查固定引导窗口包含关系与对齐；decode 要求恰好512 B，使用固定偏移并拒绝保留字节、非法计数、范围溢出、未登记覆盖的 DTB。描述中物理地址在此阶段不解引用。entry 仅把成功 decode 结果交给 unsafe ram 初始化；公开 Description 可构造这一事实已由显式 unsafe 前置条件约束，未假称类型本身证明有效性。

ram 接入先完整 FDT 解码再收集保留区。固定 firmware/boot/实际 kernel 跨度、最多16项 BootInfo、最多32项 FDT 都在同一个局部列表；向外取整因固定 RAM 页对齐且各原始范围已被包含校验，不可能绕回或越 RAM。插入排序后 cursor 单调推进，涵盖重叠、相邻、嵌套区间；补集最多52段且容量64。initialize_regions 只调用一次，计划没有部分发布路径；旧 BSS 捐赠池及其清单引用已删除。

正常启动只初始化元数据，不扫清全部可用 RAM；运行期沿用 M 的受限操作。探针地址检查发生在测试自行读写前；故意漏保留项的分配器副本可能先清该页，这是位于普通 RAM 的测试保留洞，不把该负控说成真实固件禁区访问。生产保留区不依赖读回哨兵来证明未使用。

代码责任清楚：BootInfo 解码、FDT 解析、RAM 计划、唯一页身份所有者彼此分开；I 新增函数没有多职责长路径，叶层不打印，失败在 entry 转换为可观察 panic。可信 loader 的 kernel_end、固定可读 boot 窗口和串行关闭中断是必要前提，文档没有把它们包装为不可信装载器隔离。

## 成本与余留范围

生产总计1462物理行/58446 B，含共享 ABI、平台与 S0；测试与工具另列，没有通过转移目录隐藏。正式 ELF RX153260 B、R383 B、RW1704016 B，固定页槽元数据成本保留。检查后端 prologue、call/copy/entry/panic/trap桥与 machine.s0：当前类型无超过16 B对齐，没有额外动态栈下降；生产显式调用无递归或间接调用。全部62个 VT frame求和70352 B作为当前合法启动路径的保守上界，小于131072 B栈；最大单帧8480 B不是完整调用链或实测高水位。紧急向量不使用栈。后续增加调用路径、IRQ或类型对齐需要重算。

没有未处理阻断或必需验证缺口。QEMU通过只证明固定平台与有限500ms稳定观察，当前仍无页表、普通trap、用户态、抢占、进程隔离或原生编译闭环。用户暂缓的错误码抽象、固定槽表容量及旧测试注入重构不在本轮扩大处理。可接受 K2b，并进入下一阶段 Sv39 设计/实现。
