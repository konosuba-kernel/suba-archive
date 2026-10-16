# K10 前置盘点与可执行验收方案

2026-10-16，`/root/k10_inventory`。这是依赖完成前的只读探索，**不是 K10 实施、候选冻结或验收**。盘点基线为 suba `49b2213`，biomiya `65cb036`；依据 `design/IMPLEMENTATION.md` §3–§5、`design/CONTRACTS.md`，并读取现有生产入口、测试入口及 K3–K7 验收记录。没有运行新测试，没有修改生产文件。目录中同时推进的 K8 工具只列为入口，不能算通过。

## 1. 必须先解决的三个差距

1. **正常关机尚未实现生产闭环。** `abi/contract.vt` 已保留 `SYS_POWER=66`，但 `kernel/dispatch_call.vt` 没有对应分派。`kernel/fs/worker.vt::shutdown_step` 存在，却只有旧 `tools/check_k4.py` 的测试快照插桩调用。生产 `kernel/entry.vt` 不拒绝新写入、不结束应用、不推进全系统关机。K7 GUI 的 sync 后宿主终止 QEMU 只能证明该保存流程及重挂载，不能满足“关机时已有 DMA/临时文件正常收尾”。
2. **五状态各 100 轮尚没有当前整合版本的完整证据。** K7 有真正 Submitted 时取消装载/Job 输出，各 100 轮；K5 有窗口更新后 100 轮，但普通应用仍走已删除的 `/boot/1` fixture。Ready 和流等待已有局部场景，尚未形成各 100 轮与完整账本。不能把 100 次分配/释放或一个阶段总 100 轮换算成五状态各 100 轮。
3. **性能必须实测，现有数值不等于目标通过。** `STATS_SLICE_TICKS` 仅累计 dispatch 的 call/step，漏掉 hub/FS 和一次完整 S 驻留；K7 GUI 明确不是双编译器 p99 测试。K5 秒级可见重绘和 K7 约 29 秒另一窗口操作的记录应保留。§3 的 100ms/5ms 是测量目标；报告可写“未达目标”，不得写成已达到，也不得将无界循环掩饰为环境问题。

## 2. 全矩阵入口与适用边界

下表“已有”表示存在源码或历史证据，不表示当前候选已复验通过。凡引用旧证据，必须逐项比较其实际编译输入与新候选，并写清差异不影响该断言的理由；无法证明时迁移重跑。

| §4 场景 | 可复用入口/证据 | 当前缺口与最小补齐 |
|---|---|---|
| 启动/设备 | `tools/build_system.py`、`run_system.py`；K7 GTK 正式设备组合；`check_boot_info.py`、`check_fdt.py`、`check_ram_boot.py`；`check_transport.py`、`tests/k4/independent_transport` | 正式启动命令负例矩阵：分别缺 blk/keyboard/tablet/ramfb、legacy transport 或禁 FLUSH、错误 RAM、错误 firmware。纯解析器/伪 MMIO 边界不能替代全部真实启动负例。QEMU 自己启动失败与 guest 受控拒绝分开记录。 |
| 多进程隔离 | `check_k2.py` 的 null/privileged/guard/text-write/ro-write/nx/kernel-read/registers；`tests/k4/independent_fs/protection*`；K2/K4 acceptance | 迁移到当前 `/sys/worker` FS 装载，一名持续计数/写私有页的受害者与故障者并存；补实际非法指令、语言除零 panic、写另一个进程同虚拟地址但不得改变其私有页；逐项核对退出原因和受害者哨兵/计数。不能只看父控制器存活。 |
| 资源回收 | `check_k7_kernel.py --case load_cancel/job_dma/job_owner/death`；`tests/k7/kernel_cancel.vt`；`check_k5_lifecycle.py` 的 lifecycle；K4 cancel_dma | 见下节五状态，各轮状态达成证据、完整账本与迟到完成/身份复用反例。 |
| usercopy/身份 | K3 memory/handles/waits/streams/tree/orphan_tree/spawn_invalid/allocation_failure；K4 protection/file_capacity；K5 contracts/lifecycle | 历史脚本与 RAM provider 不兼容，不能直接把“脚本仍在”作为当前通过。迁移 fixture，保留 overflow/guard/RO/长度/对象类型/stale/无关 kill/伪 Child/PID 复用断言；复用 late-token、prefix-only-usercopy 负控确认测试仍有区分力。 |
| 桌面 | `check_k5_desktop.py` GTK 8 步；`check_k5_lifecycle.py`；`check_k5_overflow.py`；K7 `check_k7_desktop.py` GTK 22+4 步 | K5 普通应用路径迁移；当前产品桌面复验重叠、拖动、焦点、合作关闭和强杀。保留原始驱动溢出和每窗队列溢出两个层次；普通 motion 合并不能替代按键 reset。 |
| 中文文本 | `check_k6.py` 348 核心用例与 K6 独立 4 例；字体许可/输出；K7 GUI 源文件与 notes 保存 | 检查 K7 GUI 是否已覆盖“中文+四字节缺字+组合字符”真实保存再打开全字节；未覆盖则最小新文档包含三类字符，进行 scalar 粒度选择/删除、保存、重启后读取。超 4MiB/非法 UTF-8 打开不破坏当前文档/旧文件，不能仅依赖纯 gap-buffer 测试。 |
| 正常持久化 | K4 filesystem/boundaries/disk_full/node_full/disk_partial/unlink_reader/transient_owner/cwd_identity；K7 remount/recovered；`check_fs_metadata.py` | 增加真实 SYS_POWER 关机协议与下面关机交错。当前 mount 回收 transient/detached 是重启生命周期兜底，不能代替关机前排空。NoSpace/节点满测试须迁移 FS 普通进程路径。 |
| 构建闭环 | `check_k7_pipeline.py` 正常/`--invalid`；`check_k7_kernel.py` job/publication/death/job_dma；`check_k7_planner.py`；`check_k7_desktop.py` | K7 修复后的冻结候选复验。源复制期间写入→Busy、冻结后旧写句柄/replace/unlink 拒绝已有具体断言；还需说明流满、读端关闭、取消、父退出分别覆盖哪个实际路径，不把同一取消案例算四项。 |
| 原生编译器 | 正在推进的 `check_k8_native.py`、`tests/k8/native.vt` | 等待 K8 实际 C0/C1/C2/C3 全文件相等、行为扰动、host oracle、退出回收及独立验收。Linux 旧固定点不能替代。 |
| 原生 kernel/S0 | K9 尚待实施 | VT、S0 分别 guest 修改并构建；sync 后新启动读取/导出，host 只搬运完整 ELF；三份字节身份、坏 ELF/超限/源竞争/取消/旧产物/搬运损坏与 host 修改拒绝；启动新行为后编译应用。 |

## 3. 五状态各 100 轮：最小而有区分力

建议一个新 `tests/k10/reclaim.vt` 控制器及一个多角色 worker，配一个 `tools/check_k10_reclaim.py`。RAM 只加载指定可信测试控制器，所有普通 worker 从初始盘 `/sys/worker` 正常 spawn；既不恢复第二个生产 loader，也不把测试 worker 赋予 desktop 权。每类 100 轮独立计数，先预热一次，保存完整每轮结果，不只输出最终绿色像素。

| 状态 | 确定性达成方法 | 杀死与验证 |
|---|---|---|
| Loading | 沿用 K7 `observe_cancel` 的真实 FS loader DMA 提交屏障：控制器启动 actor，actor 正在装载 child。记录 child 身份和 `process::State::Loading`，避免仅证明 actor 的 FileRead。 | 控制器 kill actor 的子树；IRQ 只能在恢复 U 外部中断后真实完成。保留 `--without-user-irq` 原生产 deadline 负控。原 K7 load_cancel 可复用至此，但新增状态记录应明确被取消的是谁。 |
| Ready | worker 向继承流写一次已启动标记后死循环；控制器读到标记，下一次 syscall 时通过只读观察确认目标 Ready。 | 持 Child kill，collect CANCELLED；随后重用槽，旧 Child 必须 BadHandle。记录 Ready 命中次数=100，避免 kill 抢在安装完成前。 |
| Stream wait | 父先填满 64KiB 流，child 写第 65537 字节；只读观测要求目标 Blocked 且 request 为 Write，目标 stream 无空位。 | kill 后旧缓冲完整读回，不出现 child 新字节；写端消失带来 EOF，stream/等待登记/请求均归零。现有 K3 blocked_writer 的“暂停10ms”可作为启动步骤但不能单独证明确已等待。 |
| Disk wait | 沿用 K7 job_dma 真第二块 DMA Submitted 暂停，取消 Job。 | 必须先实际提交、再撤销交付、最后真实 IRQ 完成；100 次观察 U external trap；节点/FAT/DMA/request/页归基线。保留 job_owner 父退出和十轮子树删除作为额外独立案例。 |
| Window updated | 迁移 K5 lifecycle `/boot/1`→`/sys/worker`，初始盘写入 ELF；沿用128×128更新、真实 copy 校验、代数复用。 | 每轮正常 update 后 kill；立刻失效窗口身份，分片回收后基线。另保留 first-piece-copy 撤销与 Dying kill 两交错，共102轮，其中普通100轮单独计数。 |

需要补充只读观察账本；当前公开 stats 只有 free pages、streams、FS files/requests/free blocks/free nodes/detached/block state，无法充分证明全部 handles/waits/surfaces/Child/Job 槽无漏。最小做法是在**明确测试快照**汇总有限表计数（不改变所有者状态），记录：各 owner 页、process 状态、object handle 槽、request/Wait 登记、children/jobs、window Live/Dead/surface 页、FS files/requests/detached、block Submitted/Completed。可直接调用已有 `live_count`；没有计数 API 的表由对应模块新增测试观察函数，避免跨模块裸读私有表。可选稳定生产只读 stats 接口由 ABI owner 决定。

每轮退出允许有限排空期限；到期是失败，禁止把“等待足够久后再采一个最好值”作为通过。缓存固定或一次预热后的基线独立列账。控制器自身始终活着，不能直接要求整个系统 `dispatch::quiescent()`；应比较控制器常驻基线与目标子树计账。

## 4. 正常关机的最小实现与验收形状

生产缺口应由内核 owner 实现：现有 `SYS_POWER` 通过真实启动授予的管理能力验证，接受 shutdown/reboot 两种动作；单向状态 Running→Stopping→Draining→Syncing→Power。入口拒绝新的普通 spawn 和文件修改，但已接受事务、关闭、Job 临时树清理、FS worker 与输入/只读显示继续推进。结束普通作业不等待其合作，trusted desktop 可以显示状态，最终关闭其 FS/流等引用才能满足 `shutdown_step` 前置条件。SBI SRST 失败或设备异常必须保留明确失败，不打印成功标记。K1 磁盘部署仍不在范围。

最小三正一负：

1. 正常保存→SYS_POWER shutdown→QEMU 自己退出→**同盘新 guest**读回全字节。host terminate 不能使此项通过。
2. worker 已有 Transient 文件及 Frozen Job，第二块真实写 DMA 已提交时请求关机；释放真实 IRQ，观察撤销交付、DMA 消费、临时树清理、最终 FLUSH，QEMU 自动退出；重启普通文件内容不变、临时文件消失、FAT/节点账正确。
3. 至少一个死循环应用和一个流等待应用在关机开始时活着；新写入/新spawn明确拒绝，仍能完整关机。reboot 单独记录 SRST 操作及新 Boot ID，不把重新启动宿主进程等同 guest 发起 reboot。
4. 最终 FLUSH 注入真实 EIO 或屏蔽真实完成：必须进入存储故障路径，无成功关机标记、无正常退出码。不要将故障设备永久引用算成应用泄漏。

测试可以控制 IRQ 交错与读取状态，不能调用测试专用“直接shutdown_step”来代替生产 SYS_POWER。即使已实现关机 UI，测试仍需验证普通进程伪造能力/未经授权调用被拒绝。

## 5. 设备负例如何复用

`check_k4_faults.py` 有很好的证据判定：每例新盘，blkdebug 注入挂载读、启动序号写、FLUSH、运行数据写/元数据写/读取 EIO；要求明确 guest panic 和所在启动阶段，宿主超时单独不能通过。但它消费旧 filesystem 报告、旧 root-exit/资源基线标记，以及超时插桩锚点 `if !dispatch::boot(0)`；不能原样用于当前生产。

迁移时沿用 `run_case` 的新盘/blkdebug/日志思想，改用当前 `kernel_probe` 和正式设备组合，healthy 必须到明确 U fixture 成功阶段。盘上 sector 要依据本次布局定位，不再假定 `/work/中文.vt` 是固定 node4/block193。挂载坏 CRC/layout/UTF-8/FAT cycle 可保留；新 remount transient/detached malformed 反例补足完整所有权校验。负例若切换成更具体 panic 诊断，应匹配新 phase+error，不硬编码旧70/71以掩盖分类。

错误 RAM 应运行实际 `-m 256M` 等不匹配配置并看到 boot/kernel 自己拒绝。缺 firmware 文件属于 host preflight 错误，只证明入口校验；不算 guest 检测错误固件。当前没有内置 firmware digest 检验，最小边界是正式 launcher 验证冻结 firmware/QEMU 身份并拒绝替换；绕过 launcher 的随机 BIOS 无法保证 UART 受控停机，报告应明确此信任边界而非制造不可能保证。

## 6. 实测方案，避免把不同延迟混在一起

复用固定1核/512MiB/1024×768/相同QEMU与固件，记录 host CPU、进程负载、TCG参数、磁盘cache、源码/ELF/设备身份。先单编译作为基线，再同时两个**真实 native compiler**后台编译任务，不能用忙循环冒充编译器。记录任务开始/结束区间，所有交互样本都位于两任务重叠窗口。

- 交互开始处理：用 QMP 无额外100ms sleep的事件注入方法（现 `Qmp.input` 自带 `.1s` sleep，不能直接做100ms分位估计），guest input 接收 tick→desktop 取事件 tick→目标 app 首次处理 tick 分别记录；若测 host→guest，则用 host monotonic配可观察guest acknowledgement，不能直接混减两个时钟。100–200个样本至少保存原序列、nearest-rank p50/p95/p99/max、drop/timeout，超时样本不删除。
- 可见响应：单列 QMP/GTK输入→画面实际变化时间；它含渲染/采样，不可用来替代“开始处理”。截图采样间隔给出误差上界；禁止以100ms截图轮询宣称精确p99≤100ms。
- 连续 S 驻留：trap入口最早可用 rdtime（S0）至返回U前，或明确单次唤醒后开始到下次U/WFI；将 syscall dispatch、hub、FS、cleanup/loader包含在内。boot挂载另外统计。现 `SLICE_MAX` 可以保留作细分诊断，不能命名为整体 S 上界。
- 合成：desktop 每帧开始/结束tick、copy_surface字节、ramfb写字节、损伤数；给p50/p99/max和30Hz上限下实际帧间隔。无损伤帧/空闲等待不要混入渲染耗时均值。
- 内存：boot后、桌面双编辑器稳定后、双compiler峰值、终止排空后，记录free/owner页、永久DMA/metadata/cache、ELF PT_LOAD+BSS和每程序栈；平均RSS或ELF文件大小不能替代guest页账。
- 规模：`tools/measure_kernel.py`可重用ELF段、实际frame和清单行数字段；其 `all_frames_sum` 是保守静态总和，不是动态栈高水位。compiler、kernel、boot、ABI/platform、user、tests/tools、字体分别统计，注明包括注释/空行与排除生成/历史代码。

## 7. 建议实施顺序与交付组织

K7 panic 修复/独立验收→K8→K9为正式依赖链。K10探索可提前准备，但正式候选必须绑定 K9 通过版本。K10 内部以一个 owner 集成正常关机和观察账本，测试/文档可由另一人准备；不拆强依赖的关机状态机给多个作者。

建议新增四个测试入口：`check_k10_reclaim.py`（五状态500轮）、`check_k10_shutdown.py`（真实电源/持久化交错）、`check_k10_platform.py`（设备/保护/迁移回归）、`check_k10_cost.py`（双编译器实测与规模）。命名为建议，当前均未存在。共享 snapshot/kernel reuse必须检查全部实际编译输入，冻结每组配置可复用同kernel，观察差异用明确observer hash，避免每小用例重编整个kernel。

最后由未参与生产改动者验收，提交：版本化使用参考（设备/启动/键位/错误/限制/ABI来源）、三条读者代码路径、实测成本、逐场景证据映射、原始失败/已知边界、干净目录从固定seed重建并真实启动记录。不得将旧通过报告重命名成 K10；每项须标注“本候选新跑”“输入不变有限复用”或“未完成”。正式 K10 任一必需功能失败保持未完成，性能目标未达按实测如实列账并审查有界性。
