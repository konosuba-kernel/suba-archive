# R-r1 目标修订报告

作者：`/root/scope_revision`。状态：冻结候选，等待 root 独立验收；未提交。

## 修改

- REQUIREMENTS 与 README：首版保留系统内编辑、应用编译运行、编译器原生固定点、kernel/必要 S0 完整 ELF 构建；允许 host 按字节搬运部署。明确 K0 已验收、本轮只进入 K2a。
- ARCHITECTURE：将磁盘更新循环替换为固定 RAM 引导与 guest 原生构建、持久保存、host 搬运的边界；保留原有单核隔离/桌面/存储体系。
- CONTRACTS：区分普通文件发布和延期的内核槽发布，保留普通 sync/FLUSH/正常关机；启动槽布局和调用号保留不复用，首版不授予槽写能力。修正当前入口与 S0 已实现状态。冻结 ABI 文件未改。
- IMPLEMENTATION：K4→延期 K1 的复用方向取代旧 K1→K4；K4 唯一拥有 virtio/block 低层传输与队列，K1 将来只消费其冻结底层并增加引导上层；K9 明确为原生内核/S0构建及 host 仅搬运部署，stage0 原生检查延期；K2a 不代表完整 K2。
- CODE_STYLE 0.1：仅改迁移后语言参考链接及 K0 profile/CSR/sh 已实现状态；模块、控制流、unsafe、错误、生命周期与审查规则未削弱。
- SCOPE_REVISION：集中记录用户授权、范围变化、测试 oracle 与部署的区别、旧证据适用范围。

“host 不代做构建”约束部署链。为同输入全文件比对而运行 Linux 编译器是独立测试 oracle；其输出绝不可替代 guest 输出。加载程序可以解析 ELF、设置引导参数，但不能修补 ELF。这避免把验证要求与部署限制写成冲突条款。

## 证据影响

`R-checks-r1.json` 列出历史设计 C-r3 与 K0 I-r2 的 files/inputs 中受影响身份及当前身份。旧候选、报告与验收仍留存原字节，证明旧冻结内容；不能拿旧的 ARCHITECTURE/CONTRACTS/IMPLEMENTATION/CODE_STYLE/README/REQUIREMENTS 哈希验收当前文本。规约仍为 0.1，仅编辑更正，文件哈希已变化须由本轮重新绑定。历史研究中的旧路径/规模保持原文并明确历史身份。

无 biomiya 文件、VT/S0生产代码、ABI数值、K0候选或历史验收被此节点改动。README 属于历史 K0 候选，当前修改在新 R 候选记录；K0 机器证据仍可复用，并非已对新需求文本验收。

## 检查

- 七份当前文档 39 个本地 Markdown 链接均存在；完整检查记录见 `R-checks-r1.json`。
- `git -C suba diff --check` 通过。
- 搜索 `core-s`：本次七份当前文档无陈旧路径；历史研究保持原样。
- 人工交叉核对首版门槛、K1延期、K4所有权、K9构建/部署边界、正常持久化/隔离回收/桌面/原生固定点保持；这些是作者检查，独立接受由 root 决定。
- 本节点纯文档修改，没有重新运行生产编译或 QEMU；本轮 M/I 节点负责代码与真实机器验证。
