# K2b：可信平台内存描述与实际 RAM 页池

2026-10-15。前置 suba@e8fe282（K2a 已独立验收）、biomiya@d2c6e98；使用 build/layout-p4-r1/e3.elf，SHA256 049c6e094ccd044fba3b5d357583013b77f0e8e9a98d431ad919e02b0cda2144。用户要求继续内核，暂不修上一轮评审项：不改 host 错误接口，不优化固定元数据容量，不重构旧测试框架。必要的页池输入扩展属于本次功能。

## 有界交付

固定 QEMU virt、单 hart、RV64、512 MiB RAM。内核验证 BootInfo 与其指向的复制 DTB，从固定 RAM 中排除固件、整个引导窗口、实际 kernel ELF 内存跨度、DTB reservation map、reserved-memory 子节点和 BootInfo 登记区域；将剩余整页接入已有唯一页分配器，真实 QEMU 验证跨保留洞分配/回收/清零。不实现 Sv39、IRQ、抢占或应用隔离；异常仍可信 panic。不改 ABI 字段或增加编译器语言能力。

D → (F ∥ M) → I → A。D 为本合同；F 为固定平台 FDT 检查器；M 为多段捐赠输入；I 为 BootInfo 校验/范围归一化/正式接入/组合测试；A 独立组合验收。

## F：平台 FDT 检查

唯一生产文件 `platform/fdt.vt`，模块 `platform::fdt`，可按责任增加同目录 `fdt_*.vt`（需报告显式源清单）。API：

```vt
pub const RESERVATION_CAPACITY: usize = 32;
pub struct Region { pub base: usize, pub bytes: usize }
pub struct Description {
    pub ram_base: usize, pub ram_bytes: usize,
    pub reserved_count: usize,
    pub reserved: [32]Region
}
pub enum Result { Ready(Description), Invalid, Unsupported, Limit }
pub unsafe fn inspect(data: []const u8) -> Result;
```

调用者保证输入切片存活/可读/不可变。函数不访问描述中的物理地址，不作 I/O，不改变分配器。无递归；输入最多65536 B、嵌套最多32层、节点最多512；保留项合计最多32。整段解析结束后才返回 Ready；失败不发布部分描述。

支持已观测 QEMU 使用的 v17 FDT，显式拒绝其他版本。检查 header 总长、偏移/大小/对齐、各块不交叠、reservation map 在结构块前且有界终止；检查结构 token、唯一空名根、深度闭合、属性先于子节点、nameoff/NUL、属性值/对齐边界和最终 END。所有整数大端显式解码，先减法检查再加法。未识别设备节点只验证结构，不作为 RAM。

根 #address-cells/#size-cells 必须各为2；恰好一个根级 memory 节点（memory 或 memory@...），device_type="memory"、reg 恰好一个64位地址/64位长度对且与 ABI 固定 RAM 相等，status 缺省/okay/ok；其他配置 Unsupported。内存相关重复属性/节点拒绝，不能最后值覆盖前值。嵌套/别名 memory 不得冒充有效根内存。

reservation map 项和 /reserved-memory 的直接子节点 reg 全部合并进入输出；每项非空、无溢出且完整处于固定 RAM，否则拒绝。reservation map 内重叠按规范拒绝；不同来源重叠允许 I 归并。reserved-memory 父级 cells 各为2且 ranges 必须存在并为空；只接受静态 reg（可以多对），动态 size/非空 ranges/嵌套保留节点 Unsupported。缺省或 okay/ok 状态支持；其他状态可明确 Unsupported，不能静默遗漏可能占用页。no-map/reusable 均保守保留，不释放。保留项无页对齐要求，I 向外取整。未知属性可跳过，影响地址翻译/动态分配的上述属性不能跳过。

接受真实 QEMU 原始 DTB 与经过 OpenSBI 更新的实际运行时 DTB。dtc/libfdt 只作为主机测试资料/oracle，不进入产品构建。规范：[FDT 二进制格式](https://devicetree-specification.readthedocs.io/en/latest/chapter5-flattened-format.html)、[memory/reserved-memory](https://devicetree-specification.readthedocs.io/en/latest/chapter3-devicenodes.html)。这是固定平台子集，不声称通用 DTSpec 实现。

## M：保留洞中的页身份

唯一生产所有者继续 `kernel/memory.vt`；不另造分配器，保留 Frame/allocate/release/address/stats 现有语义和1.5MiB固定槽表。增加：

```vt
pub struct Region { pub base: usize, pub bytes: usize }
pub unsafe fn initialize_regions(origin: usize, span: usize,
    regions: []const Region) -> InitResult;
```

origin 为页对齐非零地址，span 非零整页、无溢出、页数<=PAGE_CAPACITY；regions 非空最多64项，按地址严格有序且不重叠，可相邻，每段非零整页且落在[origin,origin+span)。调用者仅转交 regions 列出的可读写、长期有效、独占普通 RAM；span 中的洞既不要求可访问也不得访问。输入列表只在初始化期间借用，返回后不保留指针。所有拒绝检查在首次状态写入前，支持拒绝后重试，成功后不可重置。

以物理偏移页号映射固定 Slot，不增加每页地址字段；只有捐赠页入 free list，未捐赠槽不可分配，不算 retired。Stats.capacity 为捐赠页数（不是 span 页数），free+allocated+retired=capacity。运行期仍 O(1) 元数据操作+最多一页清零；初始化只做有界 metadata 工作，不读写任何物理页。旧 initialize([]u8) 通过单段入口复用新实现，已有组件场景不降级。私有身份索引的检查必须使用 span 边界而非 managed capacity，特别验证高偏移页和内部洞。

## I：启动接入

root 独占 entry/kernel.build、bootstrap_memory（可替换/删除）、新增 platform/boot_info.vt 与 kernel/ram.vt、集成工具和 tests/k2_ram。启动流程先关闭中断/设紧急向量，解析固定可读引导区域内 BootInfo；按 ABI 校验保留字段、计数、范围、DTB被登记保留区完整覆盖、kernel边界；当前 RAM 链仍信任加载器实际报告的 kernel_end，宿主独立 ELF 检查生成该值，不声称不可信装载器隔离。

在成功解码前不能因提供任意 DTB地址而访问固件/MMIO。复制 DTB 必须在永久引导窗口，原 DTB 已复制且没有引用后可按平台合同复用；不得越过 FDT/reserved-memory 声明保留。全固定 firmware[RAM_BASE,BOOT_BASE)、boot[BOOT_BASE,KERNEL_BASE)、实际 kernel[BASE,end) 都强制排除；接入后不再捐出旧 BSS 页池，不把 kernel 内页同时计作可分配。

将最多32个FDT项+16个BootInfo项+3固定项放入有界数组，向外页对齐、排序归并，求补集，最多64个Region。校验/构造先完成，最后一次性调用 initialize_regions；错误在分配器尚未初始化时转 panic。描述数据不保留指向外部可复用存储的引用。

测试：纯解析边界/截断/错长/溢出/重复/结构错误/容量和不支持项；多段分配器的高偏移/洞哨兵/重复释放/清零/失败不改状态；真实 QEMU 正常启动，并注入位于可用 RAM 中的非页对齐 reservation map 与 reserved-memory 洞，实际分配覆盖洞两侧，拒绝保留页；再有畸形DTB/BootInfo受控失败、漏排保留洞的负控。旧K0启动和现有组件仍验证；旧64页QEMU检查如不再适用则明确替换覆盖，不继续冒称通过。真实机器上不靠读取禁止区域来证明未使用。

所有源码/测试/工具按物理行数、字节、ELF段与单函数frame计成本；完整调用链与初始化界限另说明。不以500MiB内存全清零做日常启动操作；全量分配扫页可仅出现在有界验收探针中。候选按哈希冻结，失败保留，独立验收通过才进入下游。无自动提交。
