# K7-r1 独立验收：不通过

验收者 `/root/k4_review` 未参与 K7 生产实现。本报告只判定 K7-r1，不由后续修订覆盖。候选 SHA256 为 `b74f96dd7e3914419251e4605479053dded735e097a562b036e7d4a0c5f530b0`，正式组合为 `build/k7-system-r4`，内核 SHA256 为 `0dc8ef589248f4b6845607346b933ff7f592fba67b1b74680554d72db2ef981d`。

## 阻断结论

**正常保存、同步后的系统磁盘不能重新挂载，K7-r1 不通过。** 最终 GTK 测试首次启动完成编辑保存、编译、运行 41、修改后运行 42、编译期间另一窗口编辑保存、错误源码及新旧诊断判断、脏关闭提示、取消与最终保存，但同一磁盘第二次启动在进入桌面前 `panic reason=70`。脚本的 `wait_mapped` 失败只是表层症状，不能按 UI 等待超时处理。没有突然断电或事务恢复前提；这是正常保存结果的可重启性缺陷。

独立只读检查发现磁盘 node 10 为旧 `hello.vt`，`flags=2`（DETACHED）、generation=4、parent=3、size=73、first=last=1148。`kernel/fs/mount_check.vt` phase 2 对任意非零 flags 返回 `Fault(4,index)`；因此该合法运行期间旧 reader 对应的 detached 节点会使挂载失败。仅忽略只读磁盘观察器中的 detached 名字不会修复生产挂载；后续修复需同时维持完整块所有权校验、可见名字唯一性及回收语义，不能把拒绝坏盘降级为无条件忽略。

`first/disk.raw` 与 `reboot/disk.raw` SHA256 均为 `17a23ce4a3ae8996a9f90c9abd6a31b9d151f782af9c8dc7e52f14e680df82a9`，重启没有改变原盘。独立解析及依赖补充见 `build/k7-independent-r1/restart-audit.json`；真实启动失败见 `build/k7-desktop-r1/reboot/serial.log`。此前 ELF 与 host oracle 字节相等、无 `/jobs` 的结果只是局部正确性，不能推出整个磁盘可挂载。

## 范围与已完成验证

依据 `design/IMPLEMENTATION.md`、`CONTRACTS.md`、代码规约及 K7 交付合同，审查普通 U 编译器、Job 快照及权限、FS ELF 加载、发布替换、取消和资源生命周期、编辑器诊断版本、像素缓存及宿主适配。K8/K9 和 K10 性能完成不在范围。

独立完整身份审计核对 76 个 owned 项、66 个 input 项、种子编译器、最终系统编译输入、各程序产物、136 个初始磁盘文件及 Linux 回归输入。首次身份审计无漂移。系统 manifest 中额外五个 platform 输入没有列入候选，但已逐字节核对与依赖提交 `92c76d2d8eb23b8880d30e4579f343cb2ef1fcd4` 相同；逐项 SHA 记录于 restart-audit。返工启动后的工具变更不追认为 r1 内容。

审查重点包括 image reader 的 reader/ticket/DMA 所有权、分段装载回滚、cwd pin 转移、Job owner/member 权限与结束回收、Frozen 后旧 Read 句柄不能 seal、输出完整 ELF 校验后 replace 的提交点、诊断源摘要比较，以及改为 u32 自然对齐后 PIXELS/BACK 和 PRESENTED 行缓存的边界。未在这些已审路径定位到新的阻断；这不替代重启验收。

独立执行使用新磁盘、已核对的最终 kernel 和冻结 U fixture；未修改生产或测试源码：

| 命令（工作目录 suba） | 结果 |
| --- | --- |
| `python3 build/k7-independent-r1/audit.py` | 身份检查通过，保存 integrity.json |
| `python3 build/k7-independent-r1/replay.py job` | 通过，6.83s；权限/快照/回收边界 |
| `python3 build/k7-independent-r1/replay.py images` | 通过，9.07s；坏 ELF/cwd/相对路径与重复 spawn |
| `python3 build/k7-independent-r1/replay.py death` | 通过，4.05s；退出回收 |
| `python3 build/k7-independent-r1/replay.py job_owner` | 通过，23.45s；创建者死亡 |
| `python3 build/k7-independent-r1/replay.py invalid` | 通过，11.16s；无效编译产物不替换旧输出 |
| `python3 build/k7-independent-r1/negative.py` | 同一 U ELF 在旧 seal 缺陷内核失败 120，区分力成立；raw_run_passed=false 保留 |
| `python3 build/k7-independent-r1/restart_audit.py` | 确认真实重启 panic70、同盘身份与 detached 拒绝条件 |

negative.py 初次因读取旧报告不存在的 result 字段而在启动前 KeyError；修正独立脚本后另建 seal-negative-r2 运行。前者不计作生产失败或已执行反例，目录保留。

作者/协调者证据经读取并核对输入身份，但不冒充本验收者重跑：pipeline-r4 的真实普通 U 编译及成功/错误/取消闭环、invalid-r3、kernel final evidence 及 Linux typed ReadResult 的 26/12/48 例。GTK 最终结果原样为 passed=false。独立重跑借用已审 fixture/判别器，非新设计全部边界用例；另以旧 kernel 同 U 反例和磁盘解析区分“测试运行完成”与有效生产行为。

## 必须保留的限制

- `job-dma-r1` 第 61 轮曾返回 100，原因尚未解释；其后同 ELF 两次百轮、诊断及最终增强测试成功不能证明找到或修复该失败。本轮因确定的重启阻断，没有重复完整 100 轮压力或宣告其彻底关闭。
- UI 仍是秒级响应。最终 GTK 首次构建约 128.44s，另一窗口编辑保存约 28.66s；不满足 K10 的 100ms/p99/双编译器目标。
- r1 pipeline 报告 `compiler_sha256` 被 guest compiler 产物覆盖；已核对 seed 实物、命令来源和 guest ELF 为不同身份，不当作源漂移。后续修订应拆分字段。
- 当前 Run 操作运行当前已发布输出；失败或取消后旧有效输出可运行，不表示刚才构建成功。
- 旧 K2–K5 boot-RAM fixture 是历史提交证据，不宣称它们覆盖当前 K7 FS API；共同 transport 已接受且无关部分不重复大规模 IRQ 测试。

## 返工验收要求

修复后另冻结 K7-r2：保留本次原盘及失败；针对保存替换仍持旧 reader 的 detached 元数据提供旧坏→新好反例，检查块/节点回收与后续再次挂载；回归原有坏盘拒绝、Job/cancel 和正常发布；用最终组合完成整个 GTK 闭环及同盘重启。只有后续独立验收通过，才可完成 K7 节点提交。
