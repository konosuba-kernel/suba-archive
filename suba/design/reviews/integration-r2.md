# C-r2 定向独立复核

日期：2026-10-14。审查者 `/root/suba_design_review`，未参与受验文档编写。

**判定：通过 R1/R2 修复的架构定向复核。** C-r1 的两个阻塞已闭合；本轮不重新声称任何产品实现通过。作者已决定补充最小 C-r3，因此 C-r2 不作为最终组合交付版本，最终结论需绑定 r3 冻结清单。当前剩余的是一处已有代码的事实叙述更正，以及补全 K0 的 ramfb 16 位 MMIO 操作；没有推翻整体路线的新架构问题。

## 身份与范围

读取 `candidate-r2.json`、r1 保存副本和三份设计文档的完整差异，并复读现有 Q 的 `main.vt`、`input.vt`、`runtime/bytes.vt`。未修改受验文件，未运行产品测试。

| 更新文件 | C-r2 SHA-256 |
|---|---|
| ARCHITECTURE.md | 3cdda54565813d90decb2ee68e80c7d12a2d13e73dbdb61988fc635d7eb30a8b |
| CONTRACTS.md | 03aceb70ffd94d33801c2f73e1986066f1927401fc19fd39bb5fbccd50527ee4 |
| IMPLEMENTATION.md | 674ccbcf6632130ab6e3d5ca8d785662fbb27c33c42000075a52cfb3917032fc |

另外五个受验文件（README、需求、A-r2、B-r1 及工具链证据）与 r1 哈希相同。八个 r1 原件在 `revisions/r1/` 完整匹配原清单。

[review-r2-evidence.json](review-r2-evidence.json) 保存 25 项身份、原件保留、源码事实和清单改写实例核验，全部通过；SHA-256 `cb224d83fdf050ab10c1b0b9ea28c445cccfc033b0fa2678121be1c3c7e76abd`。这里的“源码事实核验通过”包含发现文档 start 顺序叙述错误，不能理解成证明该句文档正确。

## R1：已解决

`/jobs` 与共享可写 `/work` 分开；准备者持 Prepare 权，Frozen 是内核树权限，输入与输出具有不同权限。冻结拒绝内容写和名字修改，并包括祖先移动、旧写句柄撤权、排队请求复查、已接受写排空。作业所有者也不能解除冻结；只有结束/取消后内核可清理。这样原来的“编译器尚未打开第二个文件，被其他应用 replace”反例失效。

源采集版本在 FS owner 的串行逻辑提交边界取值，所有非 `/jobs` 的内容与名字变化增加 source_epoch；提交冻结时比较版本，变化就 Busy 并回收。计数不回绕，避免“修改后改回”伪装未变；复制自己的目标不增加源 epoch。此设计允许全局源区无关修改造成保守重试，不承诺并发任意写下总能完成快照，有限 Busy 是合理结果。没有引入长事务或超过 64 句柄的永久源锁。

现有 compiler 的输入相对 cwd 打开，不相对 manifest 所在目录打开，因此 cwd=Job 根、source/assembly 增加 `src/`、output=`out/result.elf` 可行。实际 path 上限为 96 B，manifest 上限 16 KiB；文档要求先验证改写后的限制，与源码相符。将当前 compiler.build 作相同前缀改写的检查通过。原清单、副本、策略与内容哈希一起冻结，诊断保留原路径/快照路径映射。

新增验收覆盖复制中修改、冻结后写/replace/unlink、旧句柄、src/out 分权、取消及父退出。语义足以交给 K0/K3/K4/K7实现；调用号和状态记录精确偏移仍可按原计划 K0 冻结。

## R2：已解决

普通终止范围明确为 self-exit 或自己 Child/Job 句柄的 Kill 权；collect_exit 和取消子树也要求对应权限。没有向无关进程转移此句柄的接口，裸 PID、窗口身份、路径均不是授权。desktop 的 ManageApps 不能终止自身、可信系统进程或内核。PID 重用仍检查代数，新增负例覆盖错误目标、伪造 Child 和复用身份。原来的“同用户任意按 PID kill desktop”解释已被排除。

## 其他定向检查

- 关机拒绝新用户写/新spawn，内部既有事务、临时清理、发布头与 sync 仍继续；顺序无自锁。验收增加关机时这些在途状态。
- 普通文件 16 MiB、槽 32 MiB、ELF 地址跨度 64 MiB 明确分开；从普通文件发布不能突破 16 MiB。
- 现场措辞统一为 x1–x31 加 trap CSR，x0 恒零，未变更 280/288 B 布局。
- boot 最低 PT_LOAD 段首机器 stub 与 e_entry 同为 0x80200000 的新约束合理，并加入 K0 负例；kernel 仍由自有 stage0 按经验证的 e_entry 进入。

## r3 应纠正并复核的两项

1. C-r2 称当前 Linux 生成器“在函数之后追加 start”，**与源码不符**。实际 `main.vt` 先 `rv64::start`，后 `emit_function`，最后 S0 parse。应保留新 boot 段首约束，改正其理由：现有 start 的 Linux 初始栈/x27/退出合同不能直接用于 boot，而不是现有布局顺序在函数之后。这是事实更正，不影响新约束本身。
2. 作者在 r2 冻结后指出 ramfb 的 fw_cfg selector 要求 16 位 MMIO 写。r3 应核对现有 S0 缺 `sh`，将受限 `sh` 与显式 16 位、大端、对齐包装列入 K0，并明确这是对 B-r1 一般 MMIO 建议的补充。不能仅以已有 8/32/64 位操作声称 ramfb 机器边界已齐备。具体编码仍由 K0 oracle/负例验收，不需要语言新增 u16。

其余 r1 已通过的设计分析及“完整运行容量、设备行为、延迟仍无法判定”限制继续成立。本报告仅绑定 r2，不自动批准未来 r3。
