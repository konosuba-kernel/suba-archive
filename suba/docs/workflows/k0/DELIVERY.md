# K0：内核实施起点

2026-10-14。用户授权先提交当前修复，再开始内核实施。已提交 biomiya@a86586e 和 suba@1b73487（首次保存已验收设计/规约）；后续实现独立于这两个基线。采用 dag-delivery。规范输入：design/ARCHITECTURE.md、CONTRACTS.md、IMPLEMENTATION.md 的 C-r3；CODE_STYLE.md 0.1；编译器维护版 E3 SHA256 8051f3599704a6bf180496b14632691c3463f1239946893641f65aae21969904。

本轮可验收交付为 K0 工具链和第一条正式 S-mode 启动路径；不把串口启动声称为 K1 磁盘重启、K2 隔离进程或完整内核完成。不改变语言核心语义，不放大容量除非真实清单需要；冻结种子和历史记录不改。

DAG：P / S / H / C → I → A。P/S/H/C 依赖已验收架构和规约；I 仅在各当前候选独立接受后正式启动。图无环，写入范围互斥。提前只读探索不计为节点通过。

|节点|产物/写入范围|作者|独立验收|验收标准|状态|
|---|---|---|---|---|---|
|P|biomiya Q 的 target.vt、image/rv64/main/input；有限四 profile、桥；专属 profile 工具/测试、P-*报告|/root/k0_profiles|root|Linux 不退化，固定地址/reloc/入口及桥正反例；无任意 export/外部 linker；自身可编译|P-r1已独立接受|
|S|biomiya Q s0.vt；专属 S0 工具/fixture、S-*报告|/root/k0_machine|root|CSR/sh/fence/sret/wfi/sfence.vma/有限align，独立汇编器编码对照（本机Clang；GNU安装件为空且不可执行）与操作数负例|S-r1已独立接受，见S-acceptance-r1.md|
|H|biomiya Q model/blocking/runtime 中新 host 模块；专属 host 测试、H-*报告；禁止改 main/input/compiler.build|/root/k0_host|root|语义层无 Linux syscall；具体有界 host 接口、诊断与退出失败语义不退化；提供 main/input 接入约定|H-r1已独立接受，见H-acceptance-r1.md|
|C|suba abi/platform、K0 合同、机器环境身份；biomiya compiler.build 由 root 独占|root|/root/k0_acceptance|机器可读布局唯一来源、版本与边界、编译双向探针；无宿主生成必要常量|C-r2已独立接受；r1文档冲突失败记录保留|
|I|suba 首条正式 S-mode 源与测试；跨模块清单、文档、完整组合自举/回归/资源成本证据|root|/root/k0_acceptance|实际 QEMU 正式 S0/VT 入口、CSR 与机器调用，profile段和边界；Linux固定点/扰动/受影响全套检查|I-r2已独立接受；r1观察器缺陷返工，失败记录保留|
|A|本目录 acceptance-*；不改候选|/root/k0_acceptance|对最终组合独立判定|冻结文件/依赖哈希、关键反例及实际运行证据；完整标准才通过|A已完成：acceptance-r2.md，Accepted|

候选由作者按文件哈希冻结，报告真实命令/输出/限制。root 不修改 P/S/H 受验实现；返工交作者增版。C/I 的独立验收者不得参与其编写。不能把未实现的 suba 内编译运行或磁盘加载记为 K0 通过；若既定 K0 的必需项仍缺，记录缺项并保持 K0 未完成。

P的main/input接入消费H接口：初期并行部分属于接口探索；H-r1独立接受后P才能冻结用于正式下游的完整候选。实际依赖补充为H→P，整体图仍无环；root维护compiler.build和既有工具的显式源清单。

## 目录迁移后的接续

用户将biomiya按职责迁至compiler/bootstrap/tests/tools/docs等目录。原候选与历史验收字节保留；[映射记录](I-migration-map-r1.json)关联旧路径与当前哈希。生产VT/S0及ABI合同未变，验证工具路径变化由A复核。新目录P3/P4及全套专项已完成，E3仍为049c6e094ccd044fba3b5d357583013b77f0e8e9a98d431ad919e02b0cda2144。I-r1组合候选、证据和成本现已冻结，状态为待独立验收；源码位置统一以I-candidate-r1.json为准。

## 最终判定

I-r1因正常交接后紧急异常仍被观察器接受而Rejected；I-r2修复并增加真实QEMU负控后，由未参与实现的/root/k0_acceptance独立Accepted。见[最终验收](acceptance-r2.md)及[组合说明r2](I-summary-r2.md)。I-r2候选SHA256为`d0c6a1ad2872ba0aea0fa5603e3aef0027632ce63e1b3fc37da705b7b64701f9`，443文件最终一致。P/S/H/C迁移影响已明确复核；另一次check_next.py行尾空格清理由diff/AST等价核对继承既有证据，原执行身份没有改写。

K0完成，K1/K2/K3及系统内构建闭环尚未实现。独立检查含4个真实QEMU场景、4个观察进程、20个终态序列；正常标记后的真实非法指令被拒绝。当前实现与用户目录迁移未自动提交；此前行为修复和设计基线提交保持。
