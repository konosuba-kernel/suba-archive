# K10 前置：运行期内核工作量上界审计

2026-10-16。只读源码审计，**不是 K10 验收，也不是 ≤5ms 的性能通过证明**。审计时 HEAD 为 `9d948fddc3347deed17d5394e2802078174e24aa`；`kernel/ abi/ platform/` 无工作区修改，与已接受 K7-r3 提交 `08a4d07` 的这三个目录无差异。对应已接受构建为 `build/k7-panic-production-r2/build/kernel.elf`，SHA-256 `737f4cf3c24aa4cc85753694b3e7a00de595bf74bfbfb0a9a291fce07ea6c650`。后续 Power 集成候选必须重新核对调用路径；此处不把实验快照中新增的关机协调器当成当前生产实现。

## 1. 结论及计量边界

[IMPLEMENTATION §3](../../../design/IMPLEMENTATION.md) 的原要求保持不变：初始每步数据量 ≤64KiB、表扫描 ≤64 项；指定 QEMU 环境、两个编译任务背景下，交互请求开始处理延迟 p99 ≤100ms、单次 S-mode 连续工作 ≤5ms。后两项是测量目标，不是实时保证；不能以“所有数组都有容量”或“每个 helper 都有限”代替测量。

当前主要数据通路已按页或更小粒度推进：loader 每次一页、流/窗口每次 2KiB、FS DMA 每次一块、进程回收每次 16 个页槽。未发现普通应用能把**单个叶函数**的循环次数扩大到任意用户长度、递归树深度或无限设备等待的路径。但组合预算尚未闭合：

- `entry::schedule` 在没有 Ready 用户进程而仍有工作时，重复重置批次计时器；32 片/1ms 并非连续 S 驻留上界。
- 多个运行期路径的同一步合计扫描超过 64 项，包括 Job 清理的嵌套父链、回收协调器的连续扫描、窗口撤销的内外扫描。不能将这些仅凭外层循环注释判为符合初始约束。
- 输入 IRQ 一次 hub 服务可处理 8×64 个事件，且每个 `SYN_DROPPED` 可同步清除 768 个按键状态。它有限，但组合量超过初始预算。
- UART 单字节最多轮询 2^20 次，且普通应用故障诊断会走该路径；次数有限不提供 5ms 的时间界。

本文分开计算三层：**owner 的一次 phase、一次 `hub→fs→dispatch` 调度片、从 U trap 到下一次 U 返回的连续 S 驻留**。一片包含多个 owner，批次最多 32 片，不能混称“单步”。内存清零按实际字节数计量：4KiB 页的 512 次机器字 store 不应误判为“扫描了 512 项对象表”。对象表的嵌套/连续访问则不能只算最外层。

本审计没有运行性能测试。既有 `SLICE_MAX` 仅分别包住 `dispatch::call_inner` 和 `dispatch::step_inner`，不覆盖 hub、FS、整批循环、trap 前后与 UART 的所有路径；它也不能作为连续 S 最大值。`tests/k10/observers/` 的完整资源账本扫描及测试 UART 会改变驻留时间，**不得使用观察内核的计时替代独立性能候选**。idle/WFI 等待与有效 CPU 工作需分别记录，同时保留完整 trap→U 时间，不能悄悄从总驻留中删除不利样本。

## 2. 运行期叶函数和 owner phase

以下是源码约束下的保守工作量；“数据量”指显式复制/清零，未声称包括编译器生成的所有固定大小结构赋值、栈初始化、缓存访问或设备延迟。

| 路径与真实函数 | 输入约束与一次推进上界 | 判读 |
|---|---|---|
| `memory.vt:135 clear_page`、`allocate` | 自由链 O(1)，每次准确清 4096 字节；`release` O(1)，不清整页 | 页粒度符合数据预算；无每次分配全 RAM 扫描 |
| `space.vt:87 table`、`:220 map_user`、`:254 lookup` | Sv39 最多两层中间表；一次映射最多清两个页表页及一个数据页，即 12KiB；lookup 最多 3 个 PTE | 有界；页表回收使用 children 计数，不扫描 512 项找空表 |
| `loader.vt:53 step`、`:16 next` | ELF 程序头 ≤8，映像跨度 ≤64MiB；每次一个数据/BSS/栈页，复制 ≤4KiB，加映射清零保守 ≤16KiB；栈 256 页、参数 1 页分次建立 | 叶步有界，整个装载不是一片；大 BSS 能放大总片数 |
| `dispatch_memory.vt:29 pages_step` | Allocate/Free 最多 16384 页，分配、释放、回滚均一次一页；分配连同新页表清零 ≤12KiB | 用户总量最大 64MiB，不能因此在一个 S 驻留里同步完成 |
| `space.vt:367 reap_step` | 每次最多 16 个页槽，含 Hole；总 high ≤24576；释放元数据，不清每页内容 | 回收页数不是复制字节；外部引用可使整项待排空 |
| `ranges.vt reserve/find/publish/begin_free/finish/detach` | 固定 64 个区域记录；插入/移除含位置查找和搬移，记录大小固定 | 无按用户页数逐页扫区域；与其他表扫描合计另算 |
| `usercopy.vt:8 range`、`:33 read`、`:56 write` | range 拒绝 >65536 字节及地址溢出，非对齐范围最多 17 页，每页最多 3 个 PTE；read/write 实际单次 ≤4096 字节，最多跨 2 页 | 地址检查有界，不能只凭 caller 声称安全 |
| `dispatch_stream.vt transfer_step` | admission ≤64KiB；实际 ring↔scratch↔U 两次复制，每次 ≤2048，总 ≤4096 字节 | 大请求可短传输；底层 stream 的 64KiB 容量不等于每次复制整个 ring |
| `dispatch_stream.vt wait_call/readiness` | 最多 16 个 watch，wire 256 字节；对象查找按 token 索引；等待本身不循环等就绪 | 等待阻塞交给调度；固定大小 WaitSet 不是无限用户数组 |
| `dispatch_spawn.vt:173 prepare_spawn`、`process.vt:339 arguments` | 路径/CWD ≤255 字节，参数块 4096 字节、参数项 ≤64；验证、ELF 检查、建进程、安装分 phase；参数复制 ≤4096 | 不同步读整份 ELF；普通 FS 文件上限仍为 16MiB |
| `image_reads.vt poll` | 从 FS 输出借用后复制 ≤4096 字节；普通应用使用当前 FS loader | 历史 RAM fixture 不用于推导当前加载成本 |
| `fs/namespace.vt:21 resolve_step` | 每次最多 64 节点或推进一个路径成分；每次名称比较 ≤63 字节，最坏比较量 ≤4032 字节；完整路径 ≤255 字节 | 路径游标单调推进；全路径可能需要多次 4096 节点搜索 |
| `fs/operations.vt create_operation/remove_operation/enumerate_operation`、`fs/jobs.vt job_step` | 每次节点扫描 ≤64；名称 ≤63，记录编码固定大小；创建深度最多 16，权限检查父链最多 17 | 单个搜索有界；权限父链和协调扫描需计入组合预算 |
| `fs/transfer.vt locate_step/reserve_step` | 每次最多 64 FAT 项；文件最多 16MiB/4096 块；一次请求 ≤64KiB，涉及旧块最多 17，新增块 REQUIRED ≤16 | 定位和找空闲块分片；不是每次读写同步走完整 FAT |
| `fs/transfer.vt rollback_reserved/commit_write` | 至多 16 个新块；reserve 最后一片可能再 rollback 16 项 | 失败片可有 64+16 项，不能只报 reserve 外层的 64 |
| `fs/transfer.vt read_completed/prepare_write/write_buffer` | 每次搬移 ≤4KiB；准备写的清块、清尾、覆盖复制保守合计 ≤12KiB；每次提交一个 4KiB DMA | staging 总容量 64KiB，但输入/输出也是逐 4KiB 交接 |
| `fs/worker.vt sync_scan/encode_step` | dirty 扫描 ≤64；FAT 编码 64 个 u32/256 字节；node 编码每次 32 个固定 128 字节记录，产生 4KiB，含逐记录清零和 ≤63 字节名字复制 | 单 phase 数据量远低于 64KiB；整次 SyncAll 跨多 phase 和 FLUSH |
| `fs/lifecycle.vt cleanup_step/settled` | 每次最多 64 个 FAT 或 node 项；不零写释放的数据块；settled 对每 client 的扫描游标跨步推进 | 允许读者/DMA pin 延后回收；不等于一轮就已无临时节点 |
| `fs/jobs.vt:114 job_begin`、`:270 drain_domain` | freeze/revoke 最多扫描 64 File；关闭只撤销引用，不在此递归回收全目录 | 本地扫描符合 64，合并在 dispatch/fs step 后可能超过 |
| `window.vt reserve/prepare/reap_step` | 全局 16 窗口，每 owner ≤4；表面最大 1024×768/768 页；prepare 清一页，reap 释放一页，定位最多 16 窗口 | 单表面最大 3MiB 是总容量，分配/回收不整面循环 |
| `window_surface.vt rectangle/span`、`dispatch_window.vt surface_step` | 40 字节矩形记录，stride/extent 算术检查使含 padding 总 extent ≤64KiB；span ≤2048 且不跨物理页；两次复制合计 ≤4096 | 全窗更新由多请求/多片实现，合成器在 U-mode |
| `window_events.vt list` | 固定 1056 字节缓冲清零，扫描 16 窗口并写固定 wire 记录，然后 usercopy | 数据预算内；窗口事件队列 reset 只改游标/标志，不清全部事件 |
| `objects.vt insert/drain_one/detach/available`、`children.vt cancel_parent/cancel_job/poll_next` | 每个 API 最多 64 项；Child 取消只标记直接子进程，后代经后续 reap 传播，不递归 | 单 API 有界，但连续调用不是共同 64 项预算 |
| `process.vt select`、`jobs.vt storage_pending` | 分别最多 16 进程、32 Job；token/generation 校验 O(1) | select 的“有机会运行”与真正退出 S-mode 是两回事 |
| `device/block.vt interrupt/state`、`device/virtio.vt take` | 块中断一次处理一个完成项；队列 producer delta 有容量校验；state 只检查原提交时间的 1 秒期限，无同步等待循环 | 设备未完成应返回等待/失败；不能由 1 秒故障期限推导 5ms S 上界 |
| `fs/worker.vt:143 shutdown_step` | 首次检查最多 64 File +16 请求，再创建 SyncAll；不在该函数内等待 DMA | 已有叶接口，当前 entry 未接完整 Power 协议；集成后须审计总循环 |

## 3. 必须解决或实测澄清的组合风险

### B1：无 Ready 用户时批次预算不断重置

`kernel/entry.vt:102 schedule` 外层 `loop` 在每轮新建 `started`，内层最多 32 片，每片完成 hub、FS、dispatch 后才检查 10000 ticks（10MHz 的 1ms）。因此单个慢 helper 可先超预算，32 片也可以合计超过 64KiB/64 项。

随后若 `process::select()` 返回 Idle，但 `dispatch::has_work()` 或 `storage_work` 为真，外层立即继续；只有两者均假才 `machine::idle()`。没有 Ready 用户的 Loading、分配、Dying 清理，或者等待 DMA 的 loader/Job tail，可以反复进入此路径。普通应用能通过大 BSS/大内存申请/结束大量资源增加有限总工作量；`has_work` 对 Dying/Loading 的判断还可能把“等待外部完成”当成“可继续 CPU 推进”。

这不是已证明的无限输入漏洞，也不是已实测超过 5ms；它是**当前控制结构没有连续 S 上界**的具体原因。单独减小某个 copy chunk 无法关闭该缺口。改进应把可运行推进和外部等待区分开，在整个调度入口保留预算，并明确没有 U 候选时的可中断 idle/继续政策。不能把外层重置计时器当成已让出 CPU。

### B2：清理和系统调用的多次表扫描

- `dispatch.vt:250 step_inner` 先运行 `job_tail_step`（可能扫描 64 File），再查窗口，或 `children::live_count` 64 项加 `poll_next` 64 项，或扫描 16 进程再推进其请求。即使只推进一个请求，也并非只访问一张 64 项表。
- `dispatch.vt:159 reap` 的 Handles 空表分支依次 `objects::drain_one` 64、`objects::detach` 64、`ranges::detach` 最多 64，合计最多 192 项，尚未计 step 前置工作。Tail 依次检查 Child 64、FS node 64、Window 16，成功尾端最多 144 项。短路能减少实际量，不能删除上界。
- `window.vt:210 revoke_owner` 扫 16 槽，每个 Live owner 窗口的 `revoke` 又扫描 16 槽调整 rank。利用 owner ≤4 窗口的真实约束，上界是 16+4×16=80 项，**不是**无约束 16²，也仍超过 64。
- `dispatch_stream.vt create_stream` 一次调用可能扫描 32 个 stream 槽，再两次扫描 64 handle 槽。固定容量避免无限放大，但没有统一 64 项预算。
- `fs/worker.vt:89 step` 可在同一调用串联 detached 扫描、domain 搜索、request queue 搜索及 Start phase。`fs/jobs.vt:302 domain_cleanup` 搜索 ≤32 Job，再扫描 ≤64 node；对属于该 Job 的节点，`node_depth` 最多访问 17 个父节点：单 phase 可有 1088 次父链访问。合法深目录可逼近此嵌套量；不属于用户无限深度。
- `reserve_step` 在最后 64 项扫描无空间后同步 rollback ≤16 项，失败路径也要算预算。

因此当前 `fs/worker.vt` 的 “Each call is bounded to64 entries or4KiB” 注释不能作为组合证明。建议以统一剩余访问预算或明确分离 phase 修正实际路径；已有 `fs/mount_check.vt step` 的 budget 逐访问递减方式可作为结构参考，但其通过只证明启动期 validator，不自动覆盖运行期 Job cleanup。不要通过把“项”重新定义为整棵父链来宣称达标。

### B3：输入中断的嵌套批量与 reset

`device/hub.vt:51 service` 最多 8 次 claim，每次输入中断扫描最多 2 个设备身份，再 `input.vt:255 drain` 消费最多 64 个事件。若设备在处理时补充队列，可在一次 hub 调用消费最多 512 事件，超过单片 64 项。

`input.vt:153 reset` 同步清 `HELD[768]`。raw 队列溢出会触发软件 reset；`decode` 对 `SYN_DROPPED` 的处理位于 dropping 检查之前，连续这类事件每次都触发完整清零。算术上界为每次 drain 64×768=49152 次 bool 写，一次 hub 为 393216 次 bool 写；按当前 bool 字节表示已超过 64KiB，且每次 reset 本身也有 768 状态项。这个上界要求特定设备流，不声称常规 QMP 键鼠必然产生；普通应用不能直接伪造 virtio 队列。

可验证方向是共享事件预算、reset 合并/分期或表示方式改进，同时保留释放全部旧键态的语义。正常 motion 洪峰与异常/溢出事件必须分开测，设备负例不能替代正常交互延迟。

### B4：运行期 UART 轮询不是 5ms 预算

`machine.s0:3 __suba_uart_byte` 每字节最多 2^20 次 LSR 轮询；`machine.vt:18 text` 超时停止余下输出。`entry.vt:145 handle_trap` 对 U-mode fault 输出固定诊断，`dispatch.vt step_inner` 对 root exit 输出固定前缀和最多 20 位数字。这些不是仅启动或 Panic 才执行。

字符串长度受可信调用点限制，不是用户无限串口输出；但是每个字节的有限轮询仍可能占用长 S 时间，时间检查在轮询完成后才获得机会。需要独立测正常 UART，以及故障/背压路径；若超标，考虑有时间预算的诊断或有限队列，不能将普通应用 fault 的日志排除出运行期指标。

## 4. 启动期和故障停机单列

下列循环不属于“桌面已运行、两个编译任务背景”的交互样本；它们仍需自身有限输入与故障出口，不能拿其成本混算运行期表现。

| 入口 | 为什么较大，如何有界 |
|---|---|
| `platform/fdt*`、`boot_info`、`kernel/ram.vt` | 固定最大 FDT 字节/节点/深度与保留区数组；启动一次解析、排序和区域归并 |
| `memory.vt:89 initialize_regions` | 对已接纳 RAM 页建自由链，固定 RAM 512MiB 对应最多 131072 页槽；不是运行期 allocate 的行为 |
| `space.vt:129 initialize`、映像/保留区映射 | 建立整个内核 RAM direct map、启动栈、共享分支；循环规模按固定 RAM 和验证后的有限段/保留区数 |
| 入口静态 BSS 清零、ramfb 预留 | 大型静态表/缓冲在启动清零；不能据此声称每次 request 都清同等字节，也不能把实际运行期局部 `zero` 成本漏掉 |
| `entry.vt mount_storage`、`fs/mount.vt`、`fs/mount_check.vt` | 首个 U 进程前完成 mount，decode FAT/node 分片，validator 每次预算 64；外层可连续执行很久，单独记录启动时间 |
| `dispatch::boot`、`boot_directory`、`boot_desktop_ready/abort_desktop_boot` | 首个可信 desktop 的 ELF 装载、CWD、768 页 framebuffer 映射/回滚循环；普通应用 spawn 不调用这些 boot helper |
| `device/display.vt initialize` | fw_cfg 目录最多 128 记录；DMA 同步轮询有 100ms 截止，仅用于启动配置显示 |
| `device/input.vt initialize`、`hub::initialize` | 固定两种输入设备、8 个 virtio 槽、固定队列与 config bitmap；不反复出现在 syscall 热路径 |
| `machine::halt`、S-mode emergency/Panic | 故意不返回的可信故障停机；不算用户无限循环拖死系统，也不计作正常回收成功 |

## 5. 下一步有区分力的验证

1. 在**无重型账本 observer** 的当前候选中，测 trap→下一次 U 返回、各 hub/FS/dispatch 阶段、batch 次数和 WFI 区间；分别给最大值、样本数和异常场景。只报 dispatch max 无法定位 B1。
2. 两个真实编译 Job 并行，同时由真实输入产生交互，记录输入到开始处理的 p99，以及相同时间段连续 S 最大值。测试控制器不要把等待 PPM/串口的宿主延迟误当 guest 延迟。
3. 对照“存在一个持续 Ready U 进程”和“所有可运行调用者均阻塞”两组：大 BSS FS loader、最大页申请、内存饱和失败回滚、最大页回收、等待真实 DMA 的取消。该对照能区分叶步成本与 B1 连续批次。
4. 填充 handle/child/Job 表、建立合法深目录，分别测 freeze、Job cleanup、Handles 空表末片和 Tail；记录实际扫描次数，验证 B2 组合量。四个 owner 窗口同时撤销需单列。
5. 正常 motion 洪峰、raw queue overflow、连续 reset 类设备事件分别测 hub；后两者作为设备/压力场景，不能冒充普通应用输入。保留事件重置后无 stuck key 的功能断言。
6. 当前 Power 集成后复审 quiesce→kill/drain→FS sync/FLUSH→poweroff 全链的循环、等待与超时，尤其不得在“无用户进程”阶段重新引入无总预算 busy loop。退出前若仍有 DMA/临时节点，其 ledger 与时间证据分别收集。

若独立性能工具已产生超过 5ms 的样本，应保留原始异常，优先映射到上述调用链后修复或补测；本文不提前宣布必须失败，也不将待测目标改成宽松门槛。本次只新增此审计文档，未修改生产实现。
