# K7-r2 独立验收：无法判定整体通过

验收者 `/root/k4_review` 未参与生产实现。候选 `K7-candidate-r2.json` SHA256：`64e4b379527cb24564115cab9ac8934dc398cc8e0ef9d388c9351dd96089cc69`。正式系统 `build/k7-system-r5`，生产内核 SHA256：`2f073509c6af8bce081ec60927e82db836b40fc678582ed0b831903efef88bd3`。

**功能闭环及 r1 确定性挂载缺陷修复已经验证；整体验收为无法判定，不能标为 accepted。** 原因限定为同一最终生产内核在合法磁盘正常重启时发生的一次未归类 panic 70。后续正例与诊断均成功，没有取得那类失败的具体状态证据。本报告不覆盖或改写 r1 的“不通过”结论。

## 判定依据与剩余门槛

`design/IMPLEMENTATION.md` 的 K7 强制依赖完整 K4，K4 必需条件含“create/read/write/delete/replace正常重启保留”；本轮 r1 返工也明确要求合法持久状态可重新挂载。`build/k7-kernel-remount-r1/reboot2/run.json` 对此行为留下实际失败：同一最终内核、未注入故障、合法磁盘，进入用户态前 panic 70。盘内 boot serial 已更新到 3、完整 metadata checker 为 Valid，不能再归为 r1 的 flags 拒绝问题。

该问题也不能直接判为已确认的新生产 BUG：panic 70 同时汇总挂载、设备服务、定时器失败，原日志不足以区分。实际设备 I/O 错误或超时按 CONTRACTS 允许明确停机；未知 IRQ/挂载状态错误则须修复。因此需要的是**异常路径分类**，并非增加 K10 的失败率、延迟或绝对零故障指标，也不是要求从缺失的历史日志证明不可恢复的细节。

本次定位证据如下，全部保留而不互相覆盖：

- 原始失败 `k7-kernel-remount-r1/reboot2`：3.73s，panic 70；相同输入盘的生产内核重放 3 次成功。
- 仅增加错误分支观测的 `k7-kernel-remount-diagnostic-r2`：相同 U ELF 和输入盘，12 次成功，无失败分支命中。该 snapshot 内核不同于正式生产内核。
- `k7-kernel-remount-io-r1`：相同诊断内核、并发受控 I/O，直接复制与先 fsync 复制两组各 3 次全部成功；错误元组为空。负载累计 12 GiB、临时工作集 512 MiB。此对照证明宿主 I/O 影响时序，未证明原失败由 FLUSH deadline 导致。未将预 fsync 或增大 watchdog 纳入正式工具/生产。

**解除此窄门槛的区分证据**：在相关时序/并发条件下捕获失败分支，区分 `hub::service`、FS 状态与 timer；如属 block，记录命令、elapsed、IRQ/used ring/status 与状态。若证明为真实超时/EIO 且停机符合既有故障合同，可将该场景归类而不修改成功路径；若为不期望的状态/IRQ 错误，需对应修复及同触发条件旧坏→新好对照。单纯增加成功循环次数不能代替这个区分。本报告不要求无休止试验；当前证据不足即如实保持无法判定。

## 已通过的功能与修复范围

r1 的确定性故障已闭环：同步后的合法 Transient/Detached 节点，先接受完整 codec、父链、块链长度/尾块、交叉占用及孤块检查，再进入有界回收；只有回收写回、FLUSH、启动标识写入及 FLUSH 完成才 Ready。Detached 仅不参与可见名字冲突，损坏链不被清理掩盖。目录删除在仍有 detached 子节点时返回 Busy，避免破坏父链。

精度修正：r1 原失败盘 node 10 flags=2 只能直接证明它是完整的 detached 旧版本，不能从持久盘反推当时仍有 reader，亦可能 reader 已释放而 reaper 尚未运行。构造专项则显式保持 reader，二者证据不能混用。

独立身份检查核对 83 owned、102 inputs 和 6 个候选锚定报告全部匹配。r4→r5 生产增量仅 `kernel/fs/{state,mount,mount_check,operations}.vt`；其余组合差异为 boot fixture 的 kernel 大小与 config。全部实际用户态 ELF（含 desktop/user0）逐字节不变，biomiya host_suba/typed ReadResult 的 r1 审查与 26/12/48 例回归输入身份因此保留适用。r2 已补 platform、工具和合同输入；seed/guest compiler 报告字段明确分开。

独立执行证据位于 `build/k7-independent-r2`：

| 执行/检查 | 判别与结果 |
| --- | --- |
| `audit.py` | 冻结身份、正式产物、seed/guest 身份与 r1→r2 差异通过；最终重查无漂移 |
| `remount.py` 的 new-first/new-second | 从真实 flags 1/2/3 专项盘连续启动两次，均通过；所有已发布字节保留，最终 10 nodes / 144 allocated blocks，U free 账本与盘账本一致 |
| `negative.py` 的 old-negative-r3 | 同一 U ELF、同盘，旧生产 kernel 配正确 boot/descriptor，明确 panic 70，盘未修改；与新 kernel 成功形成区分 |
| `negative.py` 的 bad-detached-chain | 新 kernel 对故意损坏的 detached 链 panic 70，拒绝前后盘 SHA 不变 |
| `validator.py` | 实际专项 metadata 派生 9 例：原 flags123 盘 Valid；各 flags 坏链/坏父、恢复为可见后的重名、孤块均拒绝 |
| `regress.py` | 新生产 kernel 下 job、images、death 三组独立真实 QEMU 回归通过 |
| `summarize.py` | GUI 最终盘源码/ELF 与 host oracle 逐字节一致；无 `/jobs/` 子项，重启确用该盘；独立证据 SHA 汇总 |

独立脚本初次准备旧 kernel 负控时，boot/descriptor 的 kernel end 与 U reservation 不匹配，产生 panic 8；两个 setup 目录保留，不计作生产失败或有效旧坏证据。修正独立 boot fixture 后另建 old-negative-r3，才得到上述有效 panic 70。纯 checker 最初对坏 FAT link 预期的具体 fault 编号有误，实际 phase1 先返回 Fault3，已按执行顺序纠正预期；拒绝判别不变。没有修改冻结生产或测试源码。

## 最终组合证据

协调者执行的 `build/k7-desktop-r2/verification.json` 为 passed=true；本验收者独立核对输入/内核身份、最终盘及截图，没有冒充亲自重跑 GTK。它完成：

1. 真正系统内编辑保存，普通 U 编译器构建并运行 41；改为 42 后重新构建运行。
2. 编译期间另一窗口中文内容编辑保存；错误源码失败；fresh/stale diagnostic 区分；脏关闭提示；取消及最终同步。
3. 同一磁盘重启，读取保存后的源码和另一窗口内容，再运行已发布程序得到 42。

`pipeline-r5`、`pipeline-invalid-r4` 以及作者 `recovered-r1`、`remount-r2`、`remount-malformed-r1` 补充真实普通 U 编译、坏产物不发布、原失败盘成功启动、65 块临时文件/flags123/父目录 Busy/完整回收，以及真实坏链/共享块/孤块拒绝。三坏盘阴性在拒绝前后磁盘 SHA 不变；pure checker 为 Fault8/9/11。作者纯 codec/metadata 141 例亦通过。上面独立重跑与作者证据身份在 JSON 中分别标明。

## 保留的边界

- 旧 `job-dma-r1` 第 61 轮 code100 仍无根因；其后同 ELF 两次百轮及增强测试成功不能声称发现或修复。它与本轮 remount panic 70 是两个独立事实。
- GUI 首次构建约145.92s，另一窗口编辑保存约29.06s；仍为秒级响应，不宣称 K10 100ms/p99 或双编译任务目标达标。
- K8 原生编译器固定点、K9 内核原生重构建、K10 整体稳定性/性能/教学交付未验收。Run 执行当前已发布产物，失败或取消后旧有效版本可运行。
- 旧 K2–K5 boot-RAM fixtures 的历史结论不冒充当前 FS API 回归；共同 transport 无生产改动，不为本阶段无故重复既有大规模 IRQ 测试。当前未知 panic 仍须单独处理。

本报告可以用于保留已验证的功能与修复工作，**不可据此将 K7 节点标成已独立接受或最终完成**。
