# A r2 更新复核

2026-10-13，验收者 `/root`；A 作者 `/root/suba_platform`。

**通过 A r2 调查验收**。`research/platform.md` 当前 SHA-256 为 `54f561782ad6d80bca0977b877d901f1f808b2dc92848a76455917b15eb0aedb`；入口证据 `platform-entry-probe.json` 为 `2f630e89d100dacf3be2137a555f71725cc228d991fa9b47d65d7b9755f246fc`。B 仍为已验收 r1。

A 在 r1 接受之后交付了补充入口证据及 r2。原判定仅代表旧候选，不静默沿用；C 尚无冻结候选，正式输入更新为 A r2/B r1。

复核修改后的容量/槽位建议、公开来源与实测边界。独立重建汇编探针并在单一 QEMU 进程运行，看到两次 OpenSBI v1.8.1、S0/S1 和正常关机；命令及完整原始输出保存为 `../research-review-entry.json`。这验证 S-mode 入口及 SRST 正常重入，仍不证明磁盘写回/装载；原失败的低 PT_LOAD 记录得到保留。

本探针使用 clang/lld，仅用于架构调查，不将其计为未来的系统内汇编能力。r2 的容量数字是 C 统一选择，ramfb 原始试验仍使用 1 GiB 稀疏盘、64×32 图案；256 MiB 磁盘和 1024×768 的最终组合尚待产品验证。
