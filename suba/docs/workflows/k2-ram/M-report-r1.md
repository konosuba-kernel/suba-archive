# K2b M-r1 多段物理页池候选

状态：冻结待 `/root` 独立验收，未提交。实施者 `/root/memory_resume`；沿用 K2a 的 `/root/physical_memory` 与 `/root/memory_resume` 原始实现，不改写其历史候选/证据。依赖已接受 D-r2；基线 suba `e8fe282`、biomiya `d2c6e98`。编译器为 `biomiya/build/layout-p4-r1/e3.elf`，SHA256 `049c6e094ccd044fba3b5d357583013b77f0e8e9a98d431ad919e02b0cda2144`。

## 改动

唯一生产页所有者仍是 `kernel/memory.vt`。新增公开数据 `Region {base, bytes}` 和 `initialize_regions(origin, span, []const Region)`；现有 initialize([]u8) 用一个局部描述符委托同一实现。未改 Frame 字段可见性、分配/清零、代数、回收和退役协议，未增每页地址表，未缩减 1.5 MiB 固定 metadata。

先用 regions_valid 完整检查 origin/span 非零、页对齐、加法边界/容量，随后验证列表非空且最多64项、每段整页非空、按地址有序不重叠、完整落在span内。相邻段可接受。首次状态写入只发生在全列表校验成功之后；失败仍可重试，成功不可重置。列表只借用到函数返回；调用期间不可变，返回后不存指针。

Slot index 是 `(page_address-origin)/PAGE_BYTES`，不是“第几个捐赠页”。新增 SPAN_PAGES 用于身份索引边界，COUNT 只记捐赠页总数供 Stats 使用。未捐赠槽保持 unallocated，不进入空闲链、不算 retired、对应地址不被读取或清零。每段按地址顺序 append 到同一链表，因此首次分配按地址递增；release 仍是原有 LIFO，不把永久分配顺序当作新的公共 API 保证。

初始化最多验证64个描述符、安装PAGE_CAPACITY个槽，每槽有限次数元数据更新；只操作自身槽表，不读写捐赠页或保留洞。运行期仍是 O(1) 元数据操作，allocate 另外清512个RV64 word。输入 list 的有效期/不可变性、实际捐赠页长期有效且独占、串行调用均由 unsafe 调用者保证；这些检查不替代 FDT/BootInfo/保留区决策。

## 验证

最终命令：

```sh
python3 -O suba/tools/check_memory.py --compiler biomiya/build/layout-p4-r1/e3.elf --out suba/build/k2-ram-m-r2
```

12个场景全部通过，记录复制为 `M-verification-r1.json`，含源码/编译器/ELF身份、编译及执行命令、实际退出码、段尺寸与编译指标。第一轮12项已通过；随后仅把注释中的“metadata writes”精确为“metadata entries”，最终轮针对最终字节在 Python -O 下通过。没有 assert 决定验收结果。

新增四个场景：

- `regions-invalid`：零/未对齐/溢出/过大span，空列表，段前越界、空段、未对齐地址/长度、段尾越界、地址溢出、无序、重复和重叠。多次失败仍 NotReady、统计为零、backing/guard 未改，最终三段相邻 donation 成功；旧单段入口再初始化返回 AlreadyInitialized。
- `regions-high`：在高虚拟地址的真实栈存储中仅捐出三页，span仍为512 MiB，最高合法 index 为131071而 managed_count仅3；前导大洞不要求实际可访问。逐个检查三页地址与整页清零，穷尽后释放最高页、重复释放拒绝、重分配清零、旧代地址/释放拒绝，另外两页数据保持，最终 free=3。初始化后将原描述符全部清零，分配仍正确，证明未保留列表指针。内部洞和捐赠范围外的全部 backing 哨兵逐字节保持。
- `regions-capacity`：65个原本完全合法的相邻单页描述符必须因列表容量而拒绝，随后借用前64项成功；完整分配、地址/清零、穷尽、回收和统计验证。第65页及其他外围哨兵不变。
- `managed-bound-negative`：在测试副本中把身份上界故意改回 COUNT，同一个高偏移探针必须退出20；能区分把 span 与 managed_count 混用的缺陷。

旧八个场景原样保留：单段初始化/拒绝后重试、完整生命周期、代数上限2的退役测试副本、ABI容量缩小到3页的测试副本、漏清零负控退出24、复用代数负控退出34，以及分配器/空程序成本探针。旧测试VT未重构；工具只增加四个case调用。副本变更不进入生产源码。

这些运行使用相同 VT 生产分配器及真实进程 RAM，不是另写的模拟分配器；它们不代替后续 I 的 S-mode 实际 RAM 接入、FDT/BootInfo校验与跨保留洞 QEMU 验证。

## 成本与边界

详细计量见 `M-cost-r1.json`，物理行数包含空行和注释。

- 生产 memory.vt：215行、8722 B，较K2a增加51行、2231 B；新Region值16 B，旧Frame/Stats布局保持。
- 测试VT共637行（新增316行）；Python入口135行（仅新增5行）。高偏移探针故意使用较大的栈 backing，测试最大单函数frame59312 B，在1 MiB测试栈内；不混入内核生产成本。
- Slot仍12 B×131072=1572864 B（1.5 MiB）。新增唯一永久状态 SPAN_PAGES 8 B；最小分配器探针 RW PT_LOAD 为1572921 B，较K2a增加8 B，其中BSS1572917 B、文件数据4 B。
- 最小分配器探针text16176 B、ELF24580 B；空入口text208 B。相对K2a分配器text增加4076 B。
- 最小探针最大单函数frame1456 B（K2a为1376 B）；完整初始化调用链包含单段委托→initialize_regions→regions_valid，具体机器集成栈仍由I核对，单函数数字不能冒充整个内核峰值。

没有页表/IRQ/用户隔离。Frame仍是复制token，release前外部映射/DMA/借用必须结束；本节点不提供进程退出回收。没有改 host错误接口、固定metadata容量策略、编译器或既有ABI；没有把暂缓的评审项混进实现。
