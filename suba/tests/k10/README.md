# K10 前置探索

这些测试在 K9 正式验收前准备，不代表 K10 通过。只有可信测试控制器从 RAM 映像启动；普通 worker 存于初始盘 `/sys/worker`，由生产 FS loader 装载。共用构建器还在保留 RAM 中放置一份未被普通 spawn 使用的 worker 副本，不能将这份副本算成FS装载来源。保留旧 K2–K5 历史测试不变。

入口（在 suba 根目录，输出目录必须全新）：

```sh
python3 tools/check_k10_lifecycle.py \
  --compiler ../biomiya/build/source-cap64-p4-r3/e3.elf \
  --source-kernel-from build/k7-panic-production-r2 \
  --mode ready --out build/k10-current-ready-r1
```

`--source-kernel-from` 验证已有冻结内核源码与产物摘要后复制其输入，允许在生产目录持续开发时做历史基线探索。后续模式可加 `--kernel-from build/k10-current-ready-r1`，只在实际观察版内核所有输入和编译器摘要相同时复用。最终候选重跑应省略历史 source 参数，并选全新输出目录；正式 K10 独立验收另外执行。

| 模式 | 实际断言 |
|---|---|
| loading | 子进程正在通过FS加载孙进程，观察真实Loading与已提交Read DMA，取消子树并验证完整账。 |
| dma | Job worker向Transient文件真实提交第二块Write DMA，取消整个Job（首轮含另一等待后代），验证撤销File权利及完整账。 |
| ready | 100轮：worker已经发送标记，观察其真实 Ready 状态，父通过Child kill，collect后旧Child失效；页/流/FS账恢复。 |
| streamwait | 100轮：父预填满64KiB，观察child真实Blocked+Write，kill后读回完整旧数据且无新字节，EOF，账恢复。 |
| windowlife | K5普通100轮迁移，窗口创建/更新/复制后取消，陈旧布局与代数拒绝，kill/collect，完整owner账；对应原要求“窗口更新后的进程”。 |
| windowupdate | 增强场景：真实WindowUpdate首2048字节后暂缓，观察Blocked+WindowCopy writing，再由U父进程Child kill，逐轮完整账。 |
| windowrace | 上述普通轮数加2轮确定性交错：first-piece CopySurface撤销、Dying DesktopKill。 |
| queue | K5窗口队列溢出迁移：100个实际QMP键边缘，65537字节流背压屏障，InputReset/Focus/CloseRequested及旧序号拒绝。 |
| identity | 通过FS加载普通worker，重跑K3 memory/streams/handles核心断言，附overflow地址、错误权利kill、超长wait记录与伪Child。 |
| isolation | 一名持续私有哨兵校验/计数的victim与故障child并存；kernel/virtio/PLIC/guard/RO/CSR/非法指令/语言除零和同地址私有写入。每次故障后排空旧计数，再要求victim生成新计数。 |
| ledgercontrol | baseline之后保留真实Ready child与流，账本门必须拒绝；kill/collect/close之后必须重新接受原基线。 |

`observer.vt`及`observers/*.vt`只追加到**输出目录的测试快照**，不改生产。测试stats selector200查Child目标的真实Ready或Blocked+Write；202捕获baseline；201比较并输出完整304项owner账。只读观察没有修改调度或制造完成事件；windowrace另有两处明确的调度交错，windowupdate暂缓首个真实复制片之后的继续工作。每份报告保留 `stage_acceptance=false`、历史输入身份、实际编译输入和observer摘要。详见[账本布局、开销与边界](LEDGER.md)。

旧 window-r1 的模式名当时是 windowupdate，实际语义对应现在 windowlife，仍是原规范“窗口更新后的进程”的有效正例，不等同于新增pending WindowCopy场景。旧探索r1/r2报告只覆盖原有部分账，不因工具升级获得新证据。完整账新增handle槽、Wait、按owner物理页、window状态与surface、FS pins/domain/grant/client。Loading/DMA复用K7真实提交后暂缓PLIC消费、取消后返回U并要求真实external trap完成的交错钩子；它们与窗口竞态钩子分开编译。selector203只读确认至少一个真实Loading进程，避免把任意文件Read误称装载中。正式K10仍须对K9之后最新候选分别跑五状态100轮。

未覆盖：正常关机协议、设备故障、完整K3迟到完成/权限矩阵、中文GUI保存、双编译器延迟、K8/K9。这套入口不能单独形成K10通过结论。`--rounds 3`可做小规模探索，正式要求仍为每状态至少100轮。
