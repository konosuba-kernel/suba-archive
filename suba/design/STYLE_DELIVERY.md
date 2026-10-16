# 代码规约交付

2026-10-14。范围：新增实现前的代码/风格规约与可编译示例，不启动 K0 或内核实现。
输入为已验收 C-r3 架构，以及当前 S-next 0.1 语言参考和编译器。

| 节点 | 依赖 | 产物/唯一写入范围 | 实施者 | 独立验收者 | 验收条件 | 状态 |
|---|---|---|---|---|---|---|
| S1 | 已验收 C-r3 | `../CODE_STYLE.md`、`../docs/examples/style/` | `/root` | `/root/suba_style_review` | 语言真实可用；不改架构；对结构、错误、unsafe、生命周期有可执行规则；区分硬约束与审查信号 | r2已独立验收 |
| S2 | S1 冻结候选 | `reviews/style-*.md` | `/root/suba_style_review` | 作为 S1 与架构组合的独立验收 | 核对规则/例外、示例编译执行、与语言及架构一致性 | r2已独立验收 |

S1→S2 无环；只有主代理写规约/示例，审查者不改受验文件。完成后在 README 添加入口；README 导航变更单独登记，不借此追认原架构候选的字节身份。原 C-r3 的设计正文保持不动。

S1-r1已冻结，身份见 `style-candidate-r1.json`。三个VT示例使用原E3编译并运行成功，记录在 `../docs/examples/style/verification.json`。README只增加规约导航，C-r3三个设计正文未改。

r1独立审查只指出调用依赖箭头方向不清，见 `reviews/style-r1.md`。旧候选保存在 `revisions/style-r1/`；r2仅修正为dispatch→所有者→编解码，冻结身份见 `style-candidate-r2.json`。示例/README未改变。

## 当前状态

2026-10-14：S1-r2及其与原架构的组合已由 `/root/suba_style_review` 独立验收通过，见 [style-r2.md](reviews/style-r2.md)。原例编译运行、4个权限负例及4个最小正对照见 [r1证据](reviews/style-r1-evidence.json)；r2仅改依赖方向，未重复执行未变示例。规约适用于后续K0–K10，当前没有启动内核实现或修改编译器生产代码。
