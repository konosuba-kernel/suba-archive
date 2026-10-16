# K7-r3 独立验收：通过

验收者 `/root/k4_review` 未参与生产实现。候选 `K7-candidate-r3.json` SHA256：`884a5e0b097db49b1d668603da696bb13c271fdb692998f83705b1ce56ece890`；89 owned、102 inputs、5 个初始证据锚点全部匹配，最终复核无漂移。生产内核 SHA256：`737f4cf3c24aa4cc85753694b3e7a00de595bf74bfbfb0a9a291fce07ea6c650`；完整组合 `build/k7-system-r6` 使用同一内核。

**本候选通过 K7 编辑、构建、运行闭环及受影响内核路径验收，可以解除 K8 的节点依赖。** 这不是 K8–K10 已完成声明。r1“不通过”和 r2“无法判定”的报告及原始失败保留，不改写历史结论。

## r2 门槛的收敛依据

本轮并非仅追加成功重试。审查确认 block 驱动将合法无新增 used buffer 的通知判为失败：Idle/Completed 的迟到通知，以及 Submitted 的 bits1+Empty 都可能被错误升级为 panic。Virtio 允许通知时没有新增 used buffer，详见 [Virtio 1.2 §2.7.7.1](https://docs.oasis-open.org/virtio/virtio/v1.2/virtio-v1.2.html)。本候选只在这些情况下保持状态；有效完成仍检查 Submitted、head、length 和 device status，异常 ring 不被放行。

旧坏→新好对照和独立重跑证明这一确定性协议缺陷已修复；Empty 不推进完成数、不释放 DMA、不重置原 deadline。生产仍使用 10,000,000 tick 超时，没有靠延长等待或跳过坏状态消除失败。新增诊断可以区分 mount/hub/runtime 路径、最后进入的挂载阶段和 block 原因；对真实后备设备 FLUSH 超时/EIO 的独立注入得到了不同且正确的元组，没有二次 trap。PLIC pending 仅新增 S-mode 只读映射，诊断不 claim、不改变队列。

这些是 r2 所缺的“相关状态机确定性缺陷修复及故障路径分类”证据，加上最终生产组合回归，足以恢复 K7 功能验收。**它们没有证明历史 `k7-kernel-remount-r1/reboot2` 的单次 panic70 就由 spurious notification 导致。** 旧样本缺失分类日志，其具体根因仍未知；受控 FLUSH/EIO 也不是那次自然故障的复现。不能把这份结论解释成旧故障已被追溯解释或系统达到零故障率。

## 独立执行与区分证据

所有独立脚本和原始结果在 `build/k7-independent-r3/`。实际执行入口：`python3 build/k7-independent-r3/{audit,notifications,faults,restart,regress,finalize}.py`，逐项单独运行；含创建目录的脚本须使用新的输出目录重跑。`restart/ledger.json` 为重启盘的独立节点/FAT 账本检查结果。JSON 报告记录证据 SHA。

| 检查 | 结果与证明范围 |
| --- | --- |
| `audit.py` | 候选、最终生产编译快照和 kernel 身份一致；9 个 notification fixture 的源码/ELF 均核对，旧 block/virtio 等于 `git show 49b2213`，其余输入相同 |
| `notifications.py` | 独立启动旧 0/4/5 与新 0–5 共 9 组；旧分别 FAIL0a/18/1f，新全部通过；真实 IRQ 完成后直接 callback 重放、RAM MMIO 全状态 Empty、坏 head/length/status 拒绝均有区分 |
| `faults.py` | 独立使用 0.2s 正控、1.3s FLUSH 延迟和 EIO5；同一正式 kernel：正控成功，超时为 mount.fs/phase9/reason7/command4/status255/used==consumed，EIO 为 mount.hub/phase8/reason6/command4/status1/used==consumed+1 |
| `restart.py` | 历史未解释故障输入盘与 r1 GTK detached 失败盘各连续启动两次；所有已发布文件全字节不变、原盘 SHA 不变、所有临时 flags 清除；分别保持 9 nodes/137 blocks 与 163 nodes/2972 blocks |
| `regress.py` | 使用新生产 kernel 与匹配 boot，重放已有独立 job、images、death 用户态 fixture，三个真实 QEMU 回归通过 |
| `finalize.py` | 独立核对最终 GUI 输入、kernel、用户 ELF、持久盘/oracle/重启盘来源；重建 observer 变换并核对 DMA 正负源码差异；证据哈希汇总通过 |

通知测试的证据边界明确：mode0 的初始完成走真实 PLIC，迟到事件用直接 callback；mode4/5 使用 RAM MMIO 模型。没有把 RAM 模型称为实际硬件产生的 spurious IRQ。错误分支诊断的 phase 是最后进入的 FS step：快速 FLUSH EIO 可为 phase8，等待超时为 phase9；`notified` 是上次 IRQ 状态，不代替当前 `irq`。

## 最终系统与 DMA 证据

协调者完成 `build/k7-desktop-r3/verification.json`，本验收者独立核对身份、持久数据及截图，没有冒称亲自重跑整个 GTK。实际链路包括：系统内编辑保存；普通 U 编译器构建并运行 41；修改为42后构建运行；编译期间另一窗口中文编辑保存；非法源码失败、fresh/stale 诊断、dirty-close、取消、最终同步；同盘重启读取并运行42。最终 `/work/hello.vt` 与 ELF 均与 host oracle 全字节相等，无 `/jobs/` 子项。host oracle 仅在 guest 完成后对照，不承担运行中的文件服务。

`build/k7-panic-load-cancel-r1` 100 轮通过；每轮等待真实已提交 DMA，终止装载者，收集 Child CANCELLED，页/节点/块回基线、文件/请求为0、block Idle。最终 selector103 要求100次实际 U 外部 trap 后的 PLIC 服务。`load-noirq-r1` 同一 U ELF、同一 observer，仅 trap.s0 两处 sie544→32 去 SEIE，保留 STIE；第一轮取消后按原 watchdog panic73。其元组 reason7、command0、status0、used=245/consumed=244、irq1、pending64，说明设备已完成但未被服务。负例的 passed=false 保留，未改成普通成功。

两者使用显式观测快照，不是字节相同的生产 kernel；生产 block/virtio 与候选一致。独立重建了全部观测变换并核对 compiled_inputs，正负差异只有 trap.s0。该证据说明真实在途请求的生命周期和 U IRQ 依赖，不能拿“坏设备停机”冒充正常回收成功。

## 复用范围与保留边界

r1 seal 修复、r2 flags1/2/3 完整验证后有界回收，以及坏链/共享块/孤块在写盘前拒绝的检查仍适用：本轮未改 metadata checker、回收或权限实现。r2 的纯141例、真实坏盘阴性、65块和父目录 Busy 专项作为先前已验证证据保留；新 kernel 的 job/images/death 和两类原盘重启补足受影响回归。r2 曾因另一个未知 panic 无法整体通过，不抹去其已验证的局部结论。

所有用户 ELF 与 system-r5 逐字节相同，biomiya host_suba/typed ReadResult 输入未变，继续使用已独立核对的 Linux input26、io12、blocking48 例。共同 transport 的未改部分保留早前接受，不机械重复大规模 IRQ 测试。

- 旧 `job-dma-r1` 第61轮 code100 仍未归因，和 remount panic70 是两个独立事实；后续成功不能宣称找到这两个原始故障的共同修复。
- 本轮 GTK 首次构建141.31s，另一窗口编辑保存34.39s。功能响应成立，K10 100ms/p99 与双编译任务目标未达标；这些时序为本机此次观察，不是硬保证。
- K8 原生固定点、K9 内核原生构建、K10 全面性能/稳定性/教学交付不在本报告通过范围。Run 运行当前已发布产物，失败或取消后保留旧有效版本。
- 若后续正常组合再次 panic，须使用新增元组定位，不能以本次验收免除返工。原始失败盘、旧报告、负控、独立日志均继续保留。

本报告及配套 JSON 完成后验收者停写，不修改或提交生产代码。
