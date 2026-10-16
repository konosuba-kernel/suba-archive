# F 实施探索记录

作者 `/root/ram_fdt`，2026-10-15。以下为冻结候选之前的探索，不作为独立验收通过。

1. 初版遵照 D-r2 将公开枚举命名 `Result`，冻结编译器实际拒绝：`I_UNSUPPORTED file=2 byte=5681`。检查 `biomiya/compiler/parse.vt` 的 `type_inner` / `named_expression`，确认该名字被显式禁用。报告 root 后，D-r3 已独立接受最小 API 改名 `InspectResult`；没有修改编译器。
2. 同模块多文件重复 `import suba::abi;` 被编译器报告 `E_NAME file=4 byte=118`；保留首文件的一份模块级导入后构建成功。
3. 首次手动跑 348 个 fixture，除 QEMU 原始与 OpenSBI 运行时 fixture 外全部通过。原因是初版要求 token padding 为零；两份真实资料均包含非零 property padding。最早的 `compatible` 长度 13，随后的 padding 为 `71 65 6d`。合同要求边界/对齐，未要求零值；实现改为不解释 padding 内容。最早手工运行未写结构化日志，其结果只在本记录和会话工具输出中留存，不称其为冻结测试记录。
4. `build/k2-f-r1/verification.json` 保留完整的 348 例运行及唯一失败：解析器接受规范允许的根前 NOP，dtc 以“不以 BEGIN_NODE 开始”拒绝。该正例保留，移除对 dtc 的通过要求；其他规范/真实有效样本仍使用独立 dtc 解码。
5. r2、r3 运行 353 例和三项缺陷副本均通过。r3 增加机器码 frame / 调用链审计。最终 r4 增加精确输入容量、属性名长度和保留节点数量边界；负控要求具体错误 Ready 输出而非任意失败。

所有构建/测试目录保留，不覆盖失败记录。正式结果见 F-report-r1 和 F-results-r1。
