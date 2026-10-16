# C-r3 最终组合独立验收

日期：2026-10-14。审查者 `/root/suba_design_review`，未参与 A/B/C 编写。

**判定：通过 C-r3 + A-r2 + B-r1 的架构设计组合验收。** C-r1 的快照与终止授权阻塞已在 r2 解决；r3 保留这些修复，并纠正现有入口发射顺序及补全所选 fw_cfg 路径需要的 16 位机器写操作。当前没有未解决的架构阻塞，可以进入 K0，按已经定义的依赖和门槛实施。该判定不是内核、桌面或原生自举已经实现的声明。

## 冻结版本

全部八个文件与 `candidate-r3.json` 独立重算匹配：

| 文件（相对 suba） | SHA-256 |
|---|---|
| README.md | ef48b90ff93657a9bd4c3f8b7a14f87117163288ef7e65fa86ea02330152ad17 |
| REQUIREMENTS.md | 6019cf0da84b6ccf49180c7bbc86db9d5c4d3597452afdc4e1cf0a531644267a |
| design/ARCHITECTURE.md | 3cdda54565813d90decb2ee68e80c7d12a2d13e73dbdb61988fc635d7eb30a8b |
| design/CONTRACTS.md | e29a3700763df7eae7c4d0036aa33a747365d4b39117cacc88404dd03d38f51f |
| design/IMPLEMENTATION.md | 502c9afc65287399f2e18ccbf63d39cabee770c14b0a01851accbe998e527770 |
| design/research/platform.md | 54f561782ad6d80bca0977b877d901f1f808b2dc92848a76455917b15eb0aedb |
| design/research/toolchain.md | c0cfeb666693fcbe607b6384ee008ad4e0d13a3755f0cc34d52f386d767db245 |
| design/research/toolchain-evidence.json | 62e285480b1af64771e8c42b3f2ddfeb206feadd163c1a4bfd491b84bc647039 |

[review-r3-evidence.json](review-r3-evidence.json) 保存 21 项独立身份/差异/源码核验，全部通过，SHA-256 `fb27106e2a6e3cfcb7f0dfe179a2aa1b7b218c3c194c00a1649fd5d91a786fed`。八个 r2 原件保存于 `revisions/r2/`，均与原清单匹配。与 r2 相比只有 CONTRACTS 和 IMPLEMENTATION 变化。

## 验收依据

完整需求追踪、运行/等待/回收反例、容量算术、A/B 与实际编译器事实核验见 [r1 报告](integration-r1.md)。R1/R2 的逐项修复验收见 [r2 报告](integration-r2.md)，其结论在本候选中保持有效：

- `/jobs` 的 Prepare/Frozen 状态及输入/输出分权，连同 source_epoch 比对、旧写权限撤销、在途修改排空与内核清理，闭合多文件构建输入的稳定性。
- 普通终止只通过 self-exit 或相应 Child/Job 权；desktop 的 ManageApps 也不能结束可信系统进程，裸 PID 不再可能被解释为授权。
- 关机拒绝新用户写而继续内部收尾；文件/槽/地址跨度限制和 trap 寄存器措辞一致。

本轮定向复核 r3 的两项差异：

1. **入口。**实读当前 `main.vt`：`rv64::start` 在普通函数和 S0 之前发射，r3 描述已更正。boot profile 要求最低 PT_LOAD 首字节就是机器 stub，且与 e_entry 同为 0x80200000；Linux 栈/x27/退出合同不能直接复用。kernel 由自有 stage0 按验证后的 e_entry 进入。该规则与 A 的入口失败证据相容；K0 的负例覆盖段/入口不一致。没有虚构当前 emitter 发射顺序来支持设计。
2. **fw_cfg 写宽度。**实读当前 S0 仅识别 sb/sw/sd，没有 sh；平台 ramfb 探针确实用 `writew 0x10100008 0x1900` 选择目录。[QEMU 官方 fw_cfg 规范源文件](https://raw.githubusercontent.com/qemu/qemu/master/docs/specs/fw_cfg.rst)规定 selector 为 16 位、MMIO 使用大端，DMA 地址寄存器为 64 位。r3 为所选 selector 路径增加受限 sh、u32 入参范围/2 B 对齐/端序/fence 包装，并列入 K0 编码负例与 K5 设备验收；无需新增语言 u16 或通用 volatile。B-r1 的一般 8/32/64 位建议由此获得明确补充，不能再解读为最终设备操作已完全足够。

没有扩张本轮为 ABI 逐字段实现审查。调用号、编码常量和模块清单在 K0 形成编译可验证的唯一来源，符合当前设计交付阶段；核心权限、所有权、等待和故障语义已能约束它们。

## 范围限制与后续门槛

本轮三次审查共记录 63 + 25 + 21 项静态/身份核验，其中包含重复核验，不能称为 109 个产品测试。未实现或实测的能力依然包括 guest 块设备/输入中断、正式 stage0 磁盘更新重启、完整桌面、移植后的编译器固定点、内核与 S0 原生构建及实际内存/延迟。它们的实现是否通过目前无法判定，必须按 K0–K10 的独立验收执行。

512 MiB 整体容量、2 MiB stage0 保留区、128 KiB 内核栈和编译器表容量仍是有明确失败边界的待测预算。不得以本次架构通过替代这些探针，也不得以宿主重新链接/替换 kernel 或 Linux-user 旧证据替代原生闭环。

可据此更新 DELIVERY 的 C/D 状态与验收登记；这类状态登记不改变受验设计内容。任何后续语义修改需要按实际影响重验，不能自动继承本候选的接受结论。
