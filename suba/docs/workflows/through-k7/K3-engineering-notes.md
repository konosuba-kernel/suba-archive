# K3 工程问题记录（K3-r1 冻结候选）

作者 `/root/memory_resume`；草稿贡献 `/root`。用户要求保留实施难点、阻塞和 BUG，供语言与架构改进。以下将已确认事实与推测区分；没有把编译拒绝一概命名为编译器缺陷。

| 类别 / 状态 | 症状与证据 | 已确认原因、处理 | 后续启示 |
|---|---|---|---|
| 语言现有限制 / 已处理 | `build/k3-compile-1/stderr.log`：E_NAME file=26 byte=115 | 同一 module 分在多个文件后，重复 import 同一别名被拒绝。把 dispatch 模块 imports 集中在 dispatch.vt，其他文件注明模块共享 imports。第二轮越过此错误。 | 模块级 imports 与文件级可读性有冲突；未来可考虑允许幂等相同导入或给出具体重复别名诊断。尚无证据是错误代码生成。 |
| 名称冲突与诊断 / 已处理 | `k3-compile-2/stderr.log`：E_NAME file=30 byte=337 | entry 导入 kernel::dispatch 后，与原 `fn dispatch` 冲突。改函数名为 handle_trap，更新有限 bind；第三轮越过该位置。 | 单一名字空间可保持简单，但 E_NAME+byte 不能直接解释“导入别名与函数名冲突”。 |
| 语言封装限制 / 已处理 | `k3-compile-3/stderr.log`：E_NAME file=28 byte=11228，`var child: process::Id = zero` | Id 字段私有，模块外不能用 zero 绕过构造。改为在 `process::Create::Ready(id)` 分支交给具名辅助函数，boot 同理；`k3-compile-4` 完整编译通过。 | 这是需要保留的身份封装约束。错误最好说明私有类型不能构造；成功分支辅助函数比伪造临时 Id 更明确。 |
| 架构缺口 / 已实测 | K2 账本只追加，重复 alloc/free 会持续增加高水位，且空页表可能留在空间 | space 增加可复用 Hole 槽及物理页→slot/children 元数据；每次 unmap 最多剪两级空表。`k3-memory-1` 验 128 次复用、精确范围拒绝及 513 页跨表边界，free 基线均恢复。 | 元数据成本显式增加 1 MiB，不用扫描 512 页表项或重复 Frame 所有权换取表面简短。高水位回收含 Hole，每步最多 16 槽。 |
| 生命周期缺口 / 已实测 | 草稿 request.active 把 Dying 仍视为有效，取消与迟到交付语义混淆 | 分离 owns(token) 和 active(token)=owns+process.deliverable；cancel 在 Dying 仍能取得元数据，copyout/finish 则拒绝。process 增加 Prepared 和 publish，装载完成不会在 argv/继承句柄安装前被调度。 | 身份存活、资源所有权和可交付资格是不同事实，不能复用一个 valid 布尔值。waits/blocked-writer迟到gate及token负控已实测，见最终报告。 |
| 内核实现缺陷 / 已修正 | 首版 Transfer 未保留 NONBLOCK，调用时可写但推进时已满可能意外阻塞 | Transfer 保存 nonblock；推进遇 WouldBlock 时以原 flags 返回或继续等待。非阻塞单进程、实际满环阻塞/唤醒及kill用例已过；NONBLOCK readiness翻转未单列定点探针。 | 即使采用单线程内核，分片之间仍会运行其他进程，瞬时 readiness 不能代替请求合同。 |
| 生命周期设计 / 已实测 | Job 的直接孩子退出后，孙进程可能尚在清理，导致 Job Done 过早 | 父进程 Tail 先等 children.settled；子树逐个沿同一门自底向上发布退出。等待用状态推进，不使用内核递归。K4 再在 Tail 添加设备/FS refs 门。 | 固定 ExitRecord 不意味着可以丢弃父子生命周期边；需明确什么时刻作业树“结束”。 |

已确认通过：`build/k3-smoke-1`、`build/k3-memory-1`、`build/k3-streams-1`。早期测得最大调用/推进片分别 35424、32661、49666 ticks（固定平台 10 MHz）；这些是 QEMU 实测值，包含当前运行环境影响，不把单组最大值当普遍延迟保证。这是早期阶段记录；最终功能证据见K3-report-r1，仍待独立验收，未提交。

## 分片时延与 spawn 拆分（过程记录）

`build/k3-tree-1` 最大连续 dispatch 片为 150792 ticks，`k3-waits-1` 为 135132 ticks。平台 timebase=10 MHz，分别约 15.08 ms / 13.51 ms，超过 IMPLEMENTATION 的单次 S 片 5 ms 目标；不能用用户 10 ms quantum 或未来 99% 交互延迟指标替代。早期测量只有最大值，尚不能断言具体成本在编译器或参数复制。

将 spawn syscall 的准备过程拆为入队、独立 4 KiB 参数快照、ELF 检查与子进程保留、逐页加载、独立 RO 参数页发布。每个父进程仅保留一个 4 KiB 请求缓冲；持久 cwd 从已发布只读参数页读取，避免维护第二份启动元数据。真实 `k3-spawn-sliced-1` 正确性通过，但最大仍 91403 ticks，尚未达目标。加入阶段标识，再区分真实长操作与宿主并行负载；未将可能的 QEMU 翻译开销当已确认根因。

额外故障证据：`k3-allocation-{0,1,2}` 分别在动态分配尚未获取页、新叶页表后、首个数据页后拒绝后续分配，均返回 NoMemory 并恢复完整 free 基线。过程复用生产 allocator/map/unmap，只有失败预算在测试副本注入。

测量边界进一步明确：`max_slice_ticks` 覆盖单次 dispatch.call / dispatch.step，不包含连续多片 schedule 的整个 S 驻留区间。K3 尚无 S-mode 外部 IRQ 入口；无 Ready 时可连续推进许多 Loading/Pages 片。K4 必须在片间建立真实 IRQ 服务边界，并分别记录连续 S 驻留、pending IRQ 到服务的最坏延迟。不会插空 WFI 美化数字，也不在 K3 宣称 K7 的双编译任务交互延迟目标完成。

隔离复测：其他节点停止启动 QEMU 后，同一 `k3-tree-sliced-1` 产物冷启动三次，最大值为 86350/86719/87082 ticks，全部是阶段103（当时为 ELF 检查＋进程创建＋继承安装），记录 `isolated-three.json`。将继承安装分离后 `k3-tree-sliced-2` 仍为76974 ticks，阶段103（检查＋创建）。因此已证实宿主并行负载不是这些超标的充分解释；继续分离检查与创建。

测试自身缺陷：`k3-spawn-invalid-1` 在恢复“保留字节”后仍返回错误，root exit124。确认探针把 cwd_offset 的第40字节误当保留字节，恢复0破坏原offset576；生产检查正确拒绝。测试改用真正保留偏移52，保留失败日志，不归类为内核或编译器 BUG。

第四轮将继承对象 attach 推迟，并去掉一层按值 Plan 转发；`k3-tree-sliced-4/isolated-three.json` 三次冷启动为52636/52328/50604 ticks（5.264/5.233/5.060 ms），仍略超目标。第五轮将 Child 退出记录保留前移到独立 ELF 检查阶段；Request 从该时刻独占未绑定 reservation，cancel_metadata 必须 abort；成功 process begin 后，bind 把所有权转入子树。另加入定点取消该窗口的真实 U 场景，防止优化制造遗漏回收。

分片新引入的生命周期缺陷（源码审查发现，已修正且定点实测通过）：Installing 已经 bind 子进程，但尚未把 Child 引用放入父句柄表；若此时父退出，仅取消子树仍会留下 held=true 的退出记录。cancel_metadata 必须 release Installing.reservation，随后子树正常回收进程；Preparing/Create 则 abort 未绑定记录。这是内核实现缺陷，不能仅称“元数据请求无需清理”。新增 cancel-install 定点杀父场景与 cancel-reservation 互相区分。

数据量边界修正：`k3-streams-final` 最大片60418 ticks，阶段105读流。原4KiB传输先 ring→scratch 再 scratch→user，实际搬运8KiB；收紧为2KiB partial，使两次合计≤4KiB。worker 测试原来每次重传 BLOCK 开头，只有整4096传输时才保持整流 pattern；改为按 total%4096 保留已发送偏移，这也是测试自身的 partial 协议缺陷。仍重新验证完整用户范围再消费任何字节，未缩小64KiB ABI或64KiB环容量。

`k3-cancel-install` 定点取消已通过（完整 free/stream/child/job 基线），但最大58746 ticks出现在 argv Copy 阶段102。将4KiB快照拆为两次2KiB复制，参数校验/cwd规范化成为单独阶段111。阻塞的单线程父进程不能在片间修改原页，复制前仍重新查PTE；取消时这三个阶段没有待释放对象。参数发布本身仍由 process.arguments 单次4KiB完成，后续真实测量继续覆盖。

## 冻结状态

最终源码/测试停止改动，候选待 `/root/ram_acceptance` 独立审查。最终 production 与 sizeof、cancel-install-final、K2 guard 均通过；完整索引见 K3-evidence-r1.json。功能正确性不代表5ms目标全面通过，真实超标保留在报告。kind32按ABI为SYS_STREAM_CREATE，kind2才是spawn；曾在进度消息解释错标签，已更正，原始日志/数值未改。没有确认的编译器错误代码生成BUG。
