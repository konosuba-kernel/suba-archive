# 测试资源账本 v1

这是测试快照内部的只读观察，不是生产 ABI。`observers/*.vt` 逐个追加到它所观察的 owner 模块：objects、request、process、space、window、ranges、image_reads、fs、block。没有从外部按地址读私有表，也不修改对象、引用或调度。block直接读取已存状态，不调用带watchdog判定的生产state()。`observer.vt` 只编排采样、比较和UART输出。源文件数保持不变，实际追加文本计入 `compiled_inputs`。

selector202 在控制器没有孩子/临时对象时采稳定基线；selector201 在每轮 kill/collect/排空后采样、与基线比较，失败返回 Invalid。每行 `K10 ledger ROUND ticks TICKS` 后是304个usize；工具要求每个样本与基线全相同。既有 `K10 round` 行保留便于阅读。

## 304项布局

| 索引 | 含义 |
|---|---|
| 0–5 | memory free、allocated、retired；kernel实际页引用数；全部私有space实际页引用数；全部surface实际页引用数 |
| 6–8 | streams、children、jobs活数 |
| 9–14 | FS free blocks、free nodes、files、requests、block state、detached |
| 15 | desktop借用framebuffer的quota页数（固定映射，不属于动态Frame） |
| 16–23 | 控制器process槽、space槽、handle数、私有页数、surface额度、pending request、Wait编码、动态range数 |
| 24 | 所有space外部页额度总和 |
| 25–31 | FS节点readers、writers、cwd引用数；File引用总数；domain活数、grant活数、client活数 |
| 32+11×process_slot，16组 | state、handles、objects attached、request pending、Wait编码、request owner、range条目、range attached、surface额度、image source活数、space_slot+1（0=无space） |
| 208+3×space_slot，16组 | live、实际私有页引用数、external额度 |
| 256+3×window_slot，16组 | state、实际surface页引用数、handle reference |

process state 使用 owner 内既有本地编码：0Vacant、1Loading、2Ready、3Running、4Blocked、5Dying、6Exited、7Prepared。window state：0Empty、1Creating、2Prepared、3Live、4Dead。Wait编码0表示无Wait；其余为1+watch数量，因此无对象的无限等待仍编码1，不会被误认为无登记。登记完整存在 Request 的 WaitSet 中，没有另一套隐藏等待链。

控制器对应的process向量和space向量清零，避免把常驻测试控制器算成待回收应用；其自身资源在16–23另列并要求不变。memory总账和FS cwd仍包含控制器，差额通过稳定基线区分。控制器不拥有测试窗口；所有窗口槽都必须回基线。身份代数单调递增及扫描游标不是资源，不参与比较。

## 页账及所有权校验

space在自己的PAGES表内遍历每个槽实际high范围，逐个验证 Frame 仍属于 memory、PAGE_INFO反向索引吻合，实际计数等于该space的count。kernel页引用也验证Frame。window在自己的FRAMES表内验证每个已分配Frame。全局要求：

```
memory.allocated = kernel_pages + private_pages + surface_pages
sum(space.external) = surface_pages + borrowed_display_charge
```

第二式只在窗口创建/销毁全部排空后采样成立：创建时quota可先预留而surface尚未分配，销毁时实际页可先释放而quota尚未撤回。不能在任意在途状态使用此等式。窗口Live/Dead及handle引用分别记录，不能只凭页数0判断窗口槽空闲。

`build/k10-ledger-windowrace-r1`在首次baseline退出49：测试漏计了可信desktop借用ramfb的768页quota，错误地把全部external当成动态surface。这是账本建模BUG，不是生产内核不变量失败；原始false日志保留。r2通过process owner内部的DISPLAY_CHARGED读取该项，借用framebuffer不加入memory.allocated等式。

DMA缓冲、block/virtio队列、FS元数据、stream缓冲、image buffer属于固定内核静态存储，不来自动态页分配器。它们的文件/BSS成本单独计账，不虚构“空闲时释放永久DMA”；对应在途状态、FS request/file/pin、image reader和stream活数均须回基线。这个观察验证动态所有者与引用生命周期，不做磁盘所有块的内容校验，也不替代I/O错误路径与关机验收。

## 开销和适用边界

每次snapshot最多扫描16×64 handle项、16 request、16 process/range/image项、4096 NodeUse+64File+32domain+16client/grant，以及各space high范围（上限16×24576页引用）、1024kernel页引用、各window allocated范围（上限16×768页引用）。全部是有界只读表扫描；**这是测试观测，故意不满足生产每步64项预算**，不进入生产二进制。

`snapshot_ticks` 记录只读遍历及不变量检查，`K10 ledger UART ticks`另记304数值的串口输出时间，10MHz换算；报告保留每个样本，不只最好值。这会延迟调度、改变IRQ交错，故不得使用此内核的SLICE_MAX、S驻留或交互延迟作为正式性能测量。采样时已排空I/O；Loading/DMA模式在采样前通过复用K7专用IRQ交错探针确认真正已提交I/O。

## 小规模探索与两处窗口交错

`--rounds N` 默认为100，探索可取3。`windowrace`会在N轮普通生命周期前加2轮：第一轮在CopySurface已交付2048字节后真实terminate+revoke，期望BadHandle/value0；第二轮在DesktopKill检查前真实标记Dying，期望保留既有退出码42。复用原K5明确的快照插桩，工具要求两标记各恰好1次。它们改变调度交错，和上面的只读账本分开记录。

`--race-observer`允许ready/streamwait/identity/isolation复用同一含交错钩子的kernel，这些模式不调用窗口路径，钩子不会命中。普通windowlife/windowupdate/queue禁止该选项，避免把竞态结果混入普通期待。正式重跑须记录source、observer和race开关的确切身份。

`ledgercontrol`是观察门的有区分力反例：实际创建一个Ready child和stream，未清理时selector201必须返回Invalid，304项样本必须异于baseline；之后正常kill/collect/close，第二次selector201必须OK且全项等于baseline。它不伪造计数，也不制造生产泄漏。工具明确记录 `expected_ledger_rejection=true`，不能把第一次拒绝伪装为普通正例。

## 完整账小轮结果（非K10验收）

以下均以旧冻结 `build/k7-system-r5` 为输入，观察内核 SHA-256 `cc75d7a0443da698260f2c661b19e7797ab07d0e1251a33332cdb12c16b11c6d`。这不是当前K9之后候选的证据；旧部分账100轮也不提升为完整账100轮。

| 输出目录 | 结果 | snapshot / UART tick范围（10MHz） |
|---|---|---|
| build/k10-ledger-windowrace-r2 | 3普通轮+2确定性交错；6份完整样本全同基线 | 77337–141590 / 30024–39533 |
| build/k10-ledger-ready-r1 | 3轮；4份样本全同基线 | 85175–141280 / 32259–38236 |
| build/k10-ledger-streamwait-r1 | 3轮；4份样本全同基线 | 86473–145966 / 32085–38847 |
| build/k10-ledger-identity-r1 | FS worker下memory/stream/handle/usercopy边界；2份样本同基线 | 90900–248996 / 34716–76601 |
| build/k10-ledger-isolation-r1 | 并存victim/9故障与隔离场景；2份样本同基线 | 97599–226859 / 47379–56972 |
| build/k10-ledger-control-r1 | 真实活资源时拒绝，排空后重新接受 | 87219–146149 / 32625–40202 |

每份 `verification.json` 保存304项原始样本、编译输入、工具及observer摘要；`tool_snapshot` 保留该次实际工具文本。采样约7.7–24.9ms、串口约3.0–7.7ms，仅量化测试自身开销，不是生产性能结论。

## Loading / DMA 交错

`loading` 和 `dma` 使用 `check_k7_kernel.observe_cancel` 的真实队列提交/PLIC暂缓探针。在普通子进程（非controller）的实际FS读或第二块Write提交时暂停IRQ消费；controller只在Submitted确实可见时取消，再重新启用PLIC并要求实际U external trap消费。每轮103计数递增且清理后304项全归基线。Loading额外要求process owner观察到至少一个State::Loading，不把普通文件读取或页准备误算装载状态。DMA首轮含额外等待后代，并检查被冻结Job的旧File read/write/sync均Denied后关闭该File。K7保留旧File跨轮的方式改为每轮关闭，以维持一致完整账基线。

这些模式只用于探索；五状态正式各100轮仍待K9及Power集成后的当前候选。真实DMA交错与窗口copy/kill交错分别编译，禁止叠加。

## 更新中的增强场景

规范原文要求“窗口更新后的进程”100轮，旧探索 `k10-explore-window-r1` 满足该语义的部分资源账；现在明确命名 `windowlife`，不会追溯判为失败。新增 `windowupdate` 是更强的pending复制场景：snapshot在真正 `window::update` 成功写首2048字节、`request::advance` 保存进度之后暂缓后续分片；U控制器查验真实Blocked+WindowCopy(writing,done=2048)，再执行普通Child kill。没有伪造状态、提前finish或从测试钩子直接terminate。每轮要求首片标记恰好一次、Cancelled collect及完整账回基线。此交错不与CopySurface/Dying两竞态钩子叠加。

`build/k10-ledger-loading-r1` 小轮探索已通过：accepted `build/k7-panic-production-r2` 冻结源，观测内核 `d33d2cbecaafddd3fff14dd9e926f92106f922a3c4835ee3163f7bad66bf6791`，3次真实Submitted Read取消、3次Loading断言和U external trap计数递增，baseline+3轮完整304项相同，运行约5.17秒。仍非K10正式验收。

`build/k10-ledger-dma-r1` 同一accepted r2观测内核的Job DMA小轮也通过：3次真实Submitted第二块Write取消，首轮含等待后代；每轮旧File读/写/sync均Denied，关闭后304项回同一baseline。该探索没有修改生产，不把static DMA buffer计为需释放动态页。

观察自身也有静态空间成本：两份304×usize快照数组合计4864字节，另有baseline标志、观察代码及专用交错状态。以accepted r2的Loading/DMA组合为例，生产ELF为1,687,608字节，观察ELF为1,777,720字节（+90,112）；ELF内存end增95,024字节。这包含全部ledger及DMA交错代码/静态量，不能仅把4864字节当成总开销，也不能把增加后的kernel页数算成普通应用泄漏。具体布局依编译器与插桩组合变化，每次以冻结报告为准。

`build/k10-ledger-update-r1` 增强场景小轮通过：accepted r2冻结源，3次真实2048字节pending WindowUpdate、U父Child kill，baseline+3次304项相等。首片日志每轮一次；精确kernel身份、耗时和报告摘要见 `ledger-exploration.json`。所有九份完整账探索汇总在该JSON，仍非正式验收。正常queue的完整账重跑、K9/Power后的五状态各100轮及增强pending100轮尚未执行；旧queue已有部分账探索结果，不提升为新的完整账证据。
