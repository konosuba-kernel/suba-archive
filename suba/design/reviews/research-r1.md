# A/B 调查独立验收

2026-10-13；验收者 `/root`。实施者分别为 `/root/suba_platform`、`/root/suba_toolchain`。

判定：**A r1、B r1 均通过调查合同**。范围是事实核验、候选路线及未知项是否足以支撑整体设计，不是内核运行通过。

受验文件 SHA-256：

- A `research/platform.md`：`763bc39faf907ef2afb3eaa1918354b82c5bb92ae8cf382c758fdd09d2455c89`。
- B `research/toolchain.md`：`c0cfeb666693fcbe607b6384ee008ad4e0d13a3755f0cc34d52f386d767db245`。
- B `research/toolchain-evidence.json`：`62e285480b1af64771e8c42b3f2ddfeb206feadd163c1a4bfd491b84bc647039`。

独立动作：阅读需求、两个候选及对应源码；重算 release 全部 18 项生产输入和实际 E3 哈希；用 Python struct 独立读取 ELF 段表，确认 RW 55,135,764 B；核对 `types.vt` 普通函数/static 匿名符号、`input.vt` 直接 fchmod 及 source/header 表、`types.module_state`；在独立临时目录重新运行 ramfb 协议探针，验证 DMA 配置和红色整帧/绿色单像素逐字节检查通过。独立探针原始记录见 `../research-review-ramfb.json`。

A 的 qtest 暂停 CPU，因此没有声称实际 guest 中断、输入、启动或重启链通过；OpenSBI 和 stage0 是设计选择而非已有实现。B 明确区分编译器运行环境与产物目标、汇编桥接与语言扩张，指出实际阻塞而非只更换 runtime。两者均未修改生产代码。

非阻塞整合事项：A 的 1 GiB 磁盘、单槽/64 MiB 是调查建议。C 将基于统一容量和开发回退需要，确定 256 MiB、两个 32 MiB 槽；不把建议值误报为已实测最终容量。B 四个 profile 的地址和桥合同由 C 确定。所有 guest 侧行为仍须经实施探针，尤其磁盘发布→正常复位→读取新内核。

后续组合由未参与 A/B/C 的 agent 独立审查，覆盖最终选择与调查证据间的一致性。
