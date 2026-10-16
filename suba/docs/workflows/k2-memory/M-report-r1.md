# M-r1 物理页所有权候选

状态：冻结后交给 `/root` 独立验收，本文不宣告 Accepted。未提交。

原始实现作者 `/root/physical_memory` 在中断前留下 `kernel/memory.vt` 和测试 backing 草稿；恢复时该 agent 已不存在。接续作者 `/root/memory_resume` 保留 free list、Frame 和代数主体，改为引用 ABI 页大小/从 RAM 容量推导表容量，澄清捐赠/回收合同，完善测试与成本证据。原 `tests/memory/common.vt` 按具体测试职责改名 `support.vt`。没有改动 biomiya、ABI 常量、机器层、入口或构建清单。

依赖是已独立接受的 R-r1（候选 SHA256 `f58658cb7b97dea87209fc7640f0912fbe26da1224d9ffa6ebf650d955e3bc49`）。编译器是迁移后 `biomiya/build/layout-p4-r1/e3.elf`，SHA256 `049c6e094ccd044fba3b5d357583013b77f0e8e9a98d431ad919e02b0cda2144`。规范 CODE_STYLE 0.1 当前文件身份见候选。

## 合同及实现

`initialize([]u8)` 只在引导期接收调用者永久独占捐赠、可写且可直接访问的普通 RAM。检查非空、页对齐、整页、地址加法和容量后才改变状态；失败可以重试，成功后不能重置。这里不解析完整 BootInfo/FDT、不推断空闲物理 RAM、不建立映射；数值检查无法替代调用者对存储来源/生命周期/排他性的证明。首次接入只能使用 kernel 的专属 BSS arena。

Frame 的 index/generation 字段均私有，公开结果为具体枚举。Frame 是可复制 token，语言不提供线性所有权；公开状态操作都是 unsafe，要求单一串行、不重入上下文。`address` 是可撤销的地址查询，不是新拥有引用。调用者必须在 release 前结束用户映射、DMA 和借用访问。模块没有可写状态表或裸 token 构造接口；统计仅返回快照。

空闲单链表使 allocate/release 为 O(1) 元数据操作。allocate 再清一页的 512 个 RV64 word，返回本代有效身份；旧 token 和重复 release 均不能回收新一代页面。generation 达到 u32 最大值后在 release 时退役，永不回绕。`capacity = free + allocated + retired` 在每次状态转换中保持；无可用页返回 Exhausted 而非 panic。

initialize 最多处理 ABI RAM 对应的 131072 个元数据项，是明确的引导期大操作；运行期不扫描整个表，address/stats/拒绝操作均 O(1)。所有普通 RAM 清零由当前 S-next 生成，没有另写汇编分配器或测试分配器。

## 验证

命令：

```sh
python3 suba/tools/check_memory.py --compiler biomiya/build/layout-p4-r1/e3.elf --out suba/build/k2-memory-m-r3
```

最终八个编译/运行场景见 `M-verification-r1.json`，每个保留 compiler/source/ELF 身份、真实命令、退出码、ELF 段和编译器指标；测试中的多个断言不冒充独立场景数。

- 未初始化 stats/allocate；零地址、非对齐、零长度、非整页、地址溢出和超容量输入拒绝；每次失败不改变状态，之后合法初始化成功；重复初始化拒绝且页面保持原值。
- 三页全部分配，地址唯一且对齐；逐字节检查完整页面清零；容量耗尽；中间页释放、重复释放、重分配、stale 地址/释放拒绝；其他已拥有页数据不变；最终统计准确，前后整页 guard 不变。
- 明确标记的 generation 上限 2 测试副本：每页两代后退役，free 下降、retired 上升，全部退役后 Exhausted，无代数回绕。
- 明确标记的 ABI RAM 缩小至三页测试副本：达到精确容量的合法 donation 成功，capacity+1 拒绝。生产 ABI/源码不改变；不声称实际捐赠并耗尽了完整 512 MiB RAM。
- 删除清零的负控必须退出 24；把每次代数固定成 1 的负控必须退出 34。两项均与正常生命周期测试使用同一源码，只替换标明的一行，证明测试能识别对应行为缺陷。
- 生产分配器最小入口与不含分配器的空入口用于成本隔离。Frame 8 B、Stats 32 B 的公开布局在初始化探针中验证；没有公开 Slot 字段供测试读取。

首轮编译遇到测试未显式使用 `core::slice_const` 的 E_TYPE，失败证据保留在 `M-attempt-initial-type-error.json`；修复的是测试调用，未放宽类型规则。第二轮八项通过；之后仅澄清生产 ownership 注释，第三轮按最终字节重新编译通过。最终证据绑定最终源码，未以早期通过状态代替。

## 成本与限制

详细计量在 `M-cost-r1.json`，统计物理行（含注释和空行）、实际文件字节、ELF PT_LOAD 与编译器 max_frame。

- 生产 `kernel/memory.vt`：164 行、6491 B。
- 测试 VT：321 行；Python 验证入口：130 行。文档/验证 JSON 单列为证据，不计作生产实现。
- 固定 131072 项表，每 Slot 布局为 12 B，元数据数组 1572864 B（1.5 MiB，完整固定平台 RAM 的约 0.293%）。这是当前简单静态表的明确成本：即使仅捐出几页，也预留全表。
- 包含分配器而不含测试 backing 的最小 ELF：RW PT_LOAD 1572913 B，其中文件数据 4 B、BSS 1572909 B。包括元数据、私有全局状态和对齐；空程序的 RW 哨兵为 1 B，不能算作分配器数据。
- 同一最小程序 text 段 12100 B；空入口 text 208 B，增量 11892 B。ELF 文件为 20484 B；BSS 不等于磁盘文件体积。
- 最小程序内最大单函数 frame 1376 B；测试程序最大 2384 B。它们不是完整 kernel/trap 调用链栈峰值，I 节点仍需实机接入预算。

普通 Linux 用户态下运行的是同一 VT 分配器和真实内存读写，可验证所有权状态机与清零边界；这不证明 S-mode 集成、全 RAM 保留区校验、用户隔离、进程退出回收或 IRQ 安全。真实 kernel BSS donation、启动输出和 K0 回归归后续 I/A 节点。
