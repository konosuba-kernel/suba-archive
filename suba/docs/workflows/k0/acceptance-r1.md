# I-r1 / A 独立验收：Rejected

验收者 `/root/k0_acceptance`，未参与 P/S/H/I 实施；此前仅验收 C 和提供只读预审。判定对象为 `I-candidate-r1.json`，SHA256 `5ec2c2947483591cf49ca1eb9aea6d3dc86bc2bf7092ae407d63cd8e30cb5faa`，420文件。候选没有被验收者修改。

## 唯一阻断：真实异常路径仍可被当成正常交接通过

`tools/check_kernel_entry.py` 正常 valid 场景只禁止文本 `suba kernel panic`。紧急 S-mode 异常走独立S0路径，输出 `!<scause>:<sepc>:<stval>`；因此正常成功标记之后立刻发生异常仍符合观察器条件。

独立反例在ignored构建副本中将 `unimp` 插在正常 `handoff accepted` 打印之后，其他行为保持。用冻结的新E3重新构建独立kernel/boot并实际启动QEMU，串口先输出成功标记，随后输出 `!0000000000000002:0000000080402630:00000000c0001073`，当前 valid 观察返回 `passed=true`。完整真实构建命令、诊断与串口见 [反例](acceptance-r1-post-marker-fault.json)。这不是仅伪造Python日志，也不是已修复的“立即杀掉进程”旧问题；500ms窗口捕获了异常，但正常场景未把它判为失败。

应让每个场景明确接受预期终态、拒绝其他普通panic/紧急异常/成功标记组合，并加入实际成功后异常负控。保留本次失败记录，更新受影响候选与证据后另冻结 I-r2。此修复若仅改变观察工具/测试与记录，不需要重跑无关生产编译器自举链。

## 已通过的独立检查

- 420文件和四个规范输入全部匹配冻结哈希；23份证据副本与原记录哈希一致；当前生产源与新P4的q-source胶囊逐文件一致。71个冻结种子输入未变。[身份核对](acceptance-r1-identity.json)
- 实际读取 E1/E2/E3 文件，均为 `049c6e094ccd044fba3b5d357583013b77f0e8e9a98d431ad919e02b0cda2144`。检查P3/P4链、胶囊哈希、阶段成功状态和当前源身份；独立运行保留的扰动编译器编译新样例，实际出现预期变更前缀。[自举抽查](acceptance-r1-bootstrap-check.json) 不重复执行完整B→P→Q链。
- 已接受 P/S/H/C 的生产 VT/S0、ABI/平台合同保持原字节。对四个变化的Python工具仅逆转路径替换，即重获各原接受哈希，说明没有混入验证算法变化。[迁移影响](acceptance-r1-migration.json) 迁移后的真实回归消费新路径；旧结论仅在该字节和路径核对后继承。
- 独立重跑新目录 ABI 真实编译/正例/错sepc负控三命令；新E3的正常交接、坏magic reason=1、可信异常三条实际QEMU路径；观察器稳定/延迟panic/立即退出三个对照；以 `python3 -O` 重跑host替代/诊断丢弃/旧model绕过三个场景，均符合当前工具期待。前三类通过不能消除上面额外反例。
- 既有435场景、新profile26/S0 167/host3的原始记录都与当前E3或其嵌入compiler.elf哈希一致。参考、系统/表示试点、guards分别记账，不混淆不同目标或重复加总。机器拒绝用例由新增支持的csrrw改为仍不支持的csrr伪指令；CSR边界另由新独立编码/反例覆盖，改动理由成立。
- 成本所有文件哈希、物理行与字节总数独立复算一致：Q生产11307行VT，runtime375行VT+19行S0；kernel152行VT+111行S0，ABI199行另列。静态内存/128KiB机器栈按实际ELF和编译统计计账。最大函数帧不是整条调用栈上界。

执行记录及哈希见 [evidence](acceptance-r1-evidence.json)，独立完整原记录另保存在 `acceptance-r1-run-1..4.json`。候选结构与源码审查未发现第二项阻断。

## 功能边界

四profile、有限桥、S0机器编码、host边界与ABI布局提供K0基础。实际boot仍是QEMU预加载kernel的测试fixture；这证明S-mode RAM交接、正式S0/VT入口、fw_cfg的16位selector及有限可信故障路径。BootInfo仅窄admission，完整FDT/reservation/CRC/保留零字节校验未完成；没有磁盘stage0、页表/抢占/进程回收、suba文件服务、系统内编译器或原生发布重启。K0最终通过与更后续节点完成不能混为一谈；本候选尚有上述验证阻断，因此此次不宣称K0完成。
