# F-r1：固定平台 FDT 描述解析候选

2026-10-15。作者 `/root/ram_fdt`；依赖已独立接受的 D-r3，等待 root 独立验收。本节点只解析可信可读切片中的不可信字节，不负责 BootInfo 指针验证、实际 RAM 访问、页池初始化或 QEMU 内核组合启动。

## 实现与接口

`platform/fdt.vt` 提供 `Region`、`Description`、`InspectResult` 和 `unsafe inspect([]const u8)`，并拥有 header / reservation map 检查；`fdt_tree.vt` 负责显式 32 层栈与结构 token；`fdt_properties.vt` 负责根、memory、reserved-memory 和静态保留子节点语义。三个文件是同一个模块，没有可变全局、递归、物理地址解引用、I/O 或外部依赖。构建必须显式列入这三个文件以及既有 `abi/contract.vt`。

范围先校验再读取；字段显式大端解码，失败不发布部分 Description。只支持 v17 / last-compatible 16、根 cells 2/2 和 ABI 指定单 RAM；缺省/ok/okay 状态支持，未知设备的 reg 不作为 RAM。保留区 map 与 reserved-memory 全部输出，map 内重叠拒绝，跨来源重叠保留给 I 归并。动态 size/alignment/alloc-ranges、地址翻译、禁用保留节点、usable-memory 限制、内存相关重复和不明确嵌套均拒绝。no-map/reusable 各自保守保留，同时设置按矛盾属性拒绝。

明确的实现上界：输入 65536 B、深度 32（含根）、节点 512（含根）、保留项合计 32；属性名按 DTSpec 限 31 B，nameoff 不会导致反复扫描整块 strings。树游标每轮至少前进 4 B；节点名/值占用输入总量，保留名字比对最多 32 次，reservation map 重叠检查最多 32×32 次，保留 reg 解码最多 32 个成功项后即限额拒绝。只有引导期同步解析，未声称 IRQ 时间预算。

## 实际验证

命令：

```sh
python3 tools/check_fdt.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/k2-f-r4
```

实际 **359 / 359** 正反例通过，另外 **3 / 3** 故障副本被区分。原记录 `build/k2-f-r4/verification.json`，冻结副本 `F-results-r1.json`。353 例的早期通过记录和 r1 的 dtc 不兼容失败均保留；探索中的语言限制与真实 padding 差异见 `F-exploration-r1.md`。

覆盖真实 QEMU dumpdtb、实际 OpenSBI 更新后的 DTB，最小有效树每个截断前缀，header/块/属性边界和溢出，重复/嵌套/别名，所有内存支持边界，以及输入、深度、节点、属性名、保留项和保留节点数量的精确界限。18 个有效资料另用 dtc 解析，DTS 留在运行目录。实际 OpenSBI 两个 no-map 固件段被原样输出。

负控故意遗漏 map、遗漏 reserved-memory 的 reg、接受重复 memory。每个反例必须正常返回预期的错误 Ready 描述（零保留区），且与正式合同期望不一致；不能以 crash、panic 或任意失败充当缺陷识别。

Linux 测试桥仅负责字节传输；既不解析输入也不复制生产判断。生产输出与 Python fixture 声明的具体 RAM/保留区逐字节比较。真实内核执行、禁止页不会分配等结论留待 I / A，F 不声称已经完成。

## 成本与可读性

生产 **553 物理行 / 23650 B**，分为 153、226、174 行三个文件；没有静态可变内存。共享 ABI 单列，不算 F 新增。测试/工具/fixture 字节与行数、所有单函数 frame 和 ELF 段详见 `F-cost-r1.json`。

本次测试 ELF 共 110593 B，RX 99332 B、R 324 B；RW 的 65537 B BSS 全部来自 Linux 测试输入缓冲，生产 F 没有 BSS。根据源声明顺序和冻结后端前导，生产函数连续机器码为 **91780 B**，不把整个测试 ELF 冒充内核增量。

最大单函数 frame 为 inspect 的 **8480 B**；逐函数机器码前导解码再组合直接调用图，F 内最长栈链为 **19360 B**：inspect → read_tree → read_property → property → reservation_property → reservation_registers → append_region → fits。包含当前编译器聚合临时值、出参和保存区，不只是局部结构大小。没有递归或间接调用。该数值不包括 I/entry 调用者、机器桥或异常；完整 128 KiB 启动栈必须由 I 再核对。

结构边界、属性语义和输出范围分开，主要函数不超过规约的约 60 行审查信号。内部 Check 为成功/无效/不支持/容量四态；只在 inspect 发布带描述的外部 InspectResult，避免把一个 544 B 聚合错误枚举在每一层传递。

## 支持边界与资料差异

这是固定平台子集，不验证所有设备绑定、phandle、总线关系或通用 DTSpec；输入切片存活/可读/不可变由调用者保证。不能直接将任意用户地址或固件/MMIO 地址传入本接口。

实际 QEMU/libfdt 的 property padding 包含非零字节；实现只检查 padding 的范围与对齐，不把内容当语义数据。根前 NOP 按规范支持，尽管当前 dtc 拒绝它；这个单独用例不以 dtc 作为裁决。依据：[DTB格式](https://devicetree-specification.readthedocs.io/en/latest/chapter5-flattened-format.html)、[memory/reserved-memory](https://devicetree-specification.readthedocs.io/en/latest/chapter3-devicenodes.html)、[属性命名长度](https://devicetree-specification.readthedocs.io/en/latest/chapter2-devicetree-basics.html)。
