# K2b 执行 DAG

依赖：已接受 K2a，提交 suba e8fe282 / biomiya d2c6e98。合同见 [CONTRACT](CONTRACT.md)。用户要求继续内核，暂不修上一轮评审项。

|节点|依赖|作者/写入范围|独立验收|状态/标准|
|---|---|---|---|---|
|D 输入合同|K2a|root；CONTRACT.md|/root/ram_acceptance|D-r3已独立接受；接口闭合，保留区不漏，固定平台子集与安全责任明确|
|F FDT描述|D|/root/ram_fdt；platform/fdt*.vt、tests/fdt、tools/check_fdt.py、F-*|root|F-r1已独立接受；真实DTB及有区分力正反例|
|M 多段页池|D|/root/memory_resume；kernel/memory.vt、tests/memory、tools/check_memory.py、M-*|root|M-r2已独立接受；洞不分配，高偏移身份正确，拒绝不改状态，旧生命周期不退化|
|I 启动集成|F+M|root；entry/build、ram/boot_info、tests/k2_ram、集成工具、当前阶段说明、I-*|/root/ram_acceptance|I-r1已独立接受；真实QEMU和漏排保留洞负控，旧边界回归|
|A 最终验收|I|/root/ram_acceptance；acceptance-*|独立判定|A-r1已通过；身份、原始证据、范围/成本、无未处理阻断|

首次派发检查：图无环，F/M写入互斥，共享入口与构建清单归root，I等F/M独立接受。探索可以先读资料，不能提前记为下游成果。旧K2a冻结记录保留原字节；本次改变的消费者由新候选/回归覆盖。

M新agent派发受全局线程上限拒绝，未启动；改复用已完成的 /root/memory_resume，须收到成功followup与D接受后才实施。

D-r2已由/root/ram_acceptance接受，/root/ram_fdt与/root/memory_resume收到正式启动通知。root在ignored build/k2-ram-draft准备I探索稿，不作为正式I交付；须F/M各自独立通过后接入。

D-r3仅将F公开Result改名InspectResult以遵循现有S-next语法；旧r1/r2合同已保存在revisions，独立判定分别保留。

## 本轮完成

D-r3、F-r1、M-r2、I-r1 与 A-r1 全部独立接受。最终组合判定见 [acceptance-r1.md](acceptance-r1.md)，冻结执行证据见 [acceptance-evidence-r1.json](acceptance-evidence-r1.json)。I候选 SHA256 `54340df9b0e9cfba40bd872fdde6c03a83a0e31497c27b8b7008c8020eccb2e4`。root 在收尾时重新核对 F/M/I 所有文件、输入、依赖及删除项，完全一致；`git diff --check` 通过，biomiya 工作树干净。未自动提交。

当前能力与构建入口见 [K2_RAM](../../K2_RAM.md)。下一阶段为 Sv39 地址空间，再推进 trap/进程生命周期；本轮未声称用户隔离完成。用户暂缓的 host 错误接口、元数据压缩与测试框架重构保持暂缓。
