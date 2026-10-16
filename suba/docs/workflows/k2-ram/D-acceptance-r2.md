# D-r2 独立增量验收

2026-10-15。判定：**通过**。合同作者 `/root`；独立验收者 `/root/ram_acceptance`，未参与实现。

核对 `D-candidate-r2.json`：当前 CONTRACT.md SHA256 为 `a642f110d9763392f4502fc4e4b1a2c6a5c7c5eb7c66be3fc49977064426af3f`，与候选相符。旧 `revisions/d-r1/CONTRACT.md` 与 D-r1 冻结哈希相符；`diff -u` 仅显示增加一条固定平台显式拒绝规则，没有其他合同变化。

增加的 memory/linux,usable-memory、chosen/linux,usable-memory-range 与保留子节点 alloc-ranges 返回 Unsupported，避免把存在额外分配限制的描述误接收为完整 RAM；它收紧支持范围，不增加接口、状态或分配所有权。对既有真实 QEMU/OpenSBI DTB 没有冲突。D-r1 的安全边界、容量和接口闭合判定继续适用。

未发现阻断。F 与 M 可依赖 D-r2 正式启动；F 必须包含新增三类属性的拒绝证据。I/A 仍待实现与独立验收。
