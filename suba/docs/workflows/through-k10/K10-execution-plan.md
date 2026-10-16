# K10 生命周期与容量矩阵执行计划

2026-10-16。**前置计划，尚未启动正式 K10。** K8 已提交 `9d948fd`；K9 和正常 Power 集成仍是前置依赖。此计划只覆盖生命周期/隔离/身份/队列/容量子矩阵，不代替设备、中文 GUI、正常关机、性能、教学文档与清洁复现的其他 K10 交付。

## 1. 候选绑定与最少内核编译

执行前由集成负责人冻结唯一候选 P：K9 已通过，Power 已集成且其必要回归已通过的**当前生产源码与原样 kernel ELF**。P 目录须有 `verification.json`、`compiled_inputs`、实际源码、`build/kernel.elf`，其编译器摘要与选定 C 相同。C 可以是已验证的宿主运行编译器，不从旧探索中猜选一个；同时保存其与原生固定点证据的关系。记录 P 的 Git revision、kernel/manifest/所有 source/assembly 哈希、C/QEMU/固件版本及哈希。

测试生成器会读当前 `tests/`、`tools/`、`user/libsuba/`，所以这些输入也须在开始前冻结并在结束后复核摘要。仅传 `--source-kernel-from P` 不会冻结所有后续测试源。观察器拼接锚点遇到 Power 改动失败时，应修正测试适配并重新冻结测试版本；不应改生产去迎合旧测试。

| 组 | 模式与轮数 | kernel 变体 | 编译/复用策略 |
|---|---|---|---|
| A | `ledgercontrol`；`ready --rounds 100`；`streamwait --rounds 100`；`windowlife --rounds 100`；`identity`；`isolation`；`queue` | P + 完整 304 项 owner ledger，只读 state/账本观察 | 第一项编译一次，后六项 `--kernel-from A-control`；每项都从 P 冻结源码再追加同一 observer，工具逐输入验证一致 |
| B | `loading --rounds 100`；`dma --rounds 100` | A + 真实 submitted DMA 确定性交错 + 真实 Loading state 检查 | loading 编译一次，dma 复用 loading；两者注入的 kernel 源码相同 |
| C | `windowupdate --rounds 100` | A + 首个 2048 字节已写后暂缓，等待 U 父普通 Child kill | 独立编译一次；不能与 A/B/D 互换 |
| D | `windowrace --rounds 1` | A + K5 first-piece CopySurface 取消、Dying DesktopKill 两处交错 | 独立编译一次；该模式执行 1 普通轮 +2 交错，共 3 轮。普通更新后的 100 轮已由 A-windowlife 覆盖 |
| S | `node_full`、`disk_full`、`disk_partial`、`boundaries`、`unlink_reader`、`unsealed_output` | **原样 P，没有资源 observer** | 六项全部 `--kernel-from P`，不新增 kernel 编译；每项独立初始盘，同盘两次启动 |

总计新增 **4 个 observer kernel 编译**，生产 P 已存在；生命周期 11 次运行 + 存储 6 项（12 次启动）。现工具每个入口仍会编译两个 U ELF 和一个 boot ELF，因此为 34 个 U 编译和 17 个小 boot 编译。不要为了少编译这些小入口去建立第二套缓存或手改 ELF；目前可靠缓存收益主要来自 kernel。P 若还没有可复用元数据，先建立一次经审核的 P 构建记录，不把这个动作隐藏成“零编译”。

A 与 D 的 kernel 不同。`--race-observer` 可把 ready/streamwait/identity/isolation/control 放到 D，但 A 的 windowlife/queue 仍需无交错 kernel，故总体仍是四种；直接留在 A 更易审查。B 仅 loading/dma，禁止与窗口交错叠加。所有缓存以 `kernel_probe.build` 的 compiler、manifest、source/assembly 全摘要检查为准；仅 ELF 文件名相同无效。

## 2. 可执行顺序模板

以下是未来执行命令，本文没有执行。工作目录为 `suba/`，由执行者将 `K10_POWER_CANDIDATE`、`K10_COMPILER` 和全新 `K10_RUN_ROOT` 绑定到正式冻结记录；不要填旧 `k7-panic-production-r2` 或探索 observer 路径。

```sh
set -eu
: "${K10_POWER_CANDIDATE:?set accepted current production Power candidate}"
: "${K10_COMPILER:?set compiler with matching candidate digest}"
: "${K10_RUN_ROOT:?set fresh formal evidence root}"

python3 tools/check_k10_lifecycle.py --compiler "$K10_COMPILER" \
  --source-kernel-from "$K10_POWER_CANDIDATE" \
  --mode ledgercontrol --out "$K10_RUN_ROOT/a-control"

for k10_mode in ready streamwait windowlife identity isolation queue; do
  python3 tools/check_k10_lifecycle.py --compiler "$K10_COMPILER" \
    --source-kernel-from "$K10_POWER_CANDIDATE" \
    --kernel-from "$K10_RUN_ROOT/a-control" \
    --mode "$k10_mode" --rounds 100 --out "$K10_RUN_ROOT/a-$k10_mode" || exit 1
done

python3 tools/check_k10_lifecycle.py --compiler "$K10_COMPILER" \
  --source-kernel-from "$K10_POWER_CANDIDATE" \
  --mode loading --rounds 100 --out "$K10_RUN_ROOT/b-loading"
python3 tools/check_k10_lifecycle.py --compiler "$K10_COMPILER" \
  --source-kernel-from "$K10_POWER_CANDIDATE" \
  --kernel-from "$K10_RUN_ROOT/b-loading" \
  --mode dma --rounds 100 --out "$K10_RUN_ROOT/b-dma"

python3 tools/check_k10_lifecycle.py --compiler "$K10_COMPILER" \
  --source-kernel-from "$K10_POWER_CANDIDATE" \
  --mode windowupdate --rounds 100 --out "$K10_RUN_ROOT/c-windowupdate"
python3 tools/check_k10_lifecycle.py --compiler "$K10_COMPILER" \
  --source-kernel-from "$K10_POWER_CANDIDATE" \
  --mode windowrace --rounds 1 --out "$K10_RUN_ROOT/d-windowrace"

for k10_case in node_full disk_full disk_partial boundaries unlink_reader unsealed_output; do
  python3 tools/check_k10_storage.py --compiler "$K10_COMPILER" \
    --kernel-from "$K10_POWER_CANDIDATE" \
    --case "$k10_case" --out "$K10_RUN_ROOT/s-$k10_case" || exit 1
done
```

脚本式批量执行时启用失败即停，或逐条检查返回值后继续；不能在首个控制组失败后仍把其 kernel 当有效测试基线。每个 out 必须此前不存在。优先 A-control，因为它主动保留 child/stream 资源，必须先观察账本拒绝，清理后再恢复基线；这使后面大量“恢复成功”有一个能识别泄漏的负控制。

当前工具故意写 `stage_acceptance=false` 和 preparatory scope，不应改旧探索报告字段来制造正式通过。正式 reviewer 可在 K10 总验收记录中引用这批新运行的 raw evidence、输入身份及子项结论；若团队需要 tool 区分正式运行标签，应先单独评审标签变更再冻结，不能把标签本身当验收。被接受的生产 P 与观察版 kernel 摘要必须分别列出。

## 3. 每项必须核对什么

| 子项 | 不能只看绿色像素；还需核对 |
|---|---|
| A-control | baseline→保留 child/stream 时明确拒绝→kill/collect/close 后接受；304 项含测试控制器资源分列，不能把控制器槽混入工作负载零基线 |
| ready / streamwait / windowlife | 各正好 100 个完成轮记录、101 个基线/轮后 ledger；Ready/Blocked+Write 实态、流满后旧字节不变、更新完成后窗口撤销分别对应实际行为 |
| loading | 100 轮；真实 Loading state + 已提交文件 Read DMA + 取消后真实外部 IRQ；不是通过延迟猜装载中，也不是 RAM loader |
| dma | 100 轮；真实第二块 Write DMA 提交后取消，第一轮包含另一个等待后代；File 权利撤销、临时节点/请求/pin/页恢复，不把“process 不见了”当回收完 |
| windowupdate | 100 轮；每轮真实首 2048 字节复制标记、Blocked+WindowCopy writing、由 U 父 Child kill；101 个完整 ledger |
| windowrace | 3 完成轮/4 ledger；两个交错标记及预期 BadHandle/Dying 拒绝必须出现；不能只检查普通轮 |
| identity | 当前 FS worker 的 memory/streams/handles 核心断言，溢出地址、越权 kill、超长 wait、伪 Child 等真实拒绝；无 panic；最终账恢复 |
| isolation | victim 持续校验私有哨兵；每次 fault 后排空旧计数并等待新计数，避免“事先缓存的进展”冒充持续存活；覆盖 CSR、非法指令、RO/guard/kernel/设备地址及除零 |
| queue | 实际 QMP 键边缘及 guest 队列事件，对应 InputReset/Focus/CloseRequested 和旧序号拒绝；确认测试没有因为 Power 新接键位而意外触发关机 |
| storage 六项 | 每项两次同盘启动都通过；guest sync、空闲块/节点账、旧文件仍可读；host 比较完整路径映射、内容哈希/长度/代数，FAT 已分配块集合恰好等于唯一归属链，无 temp/detached 遗留；两次 startup serial 区分 |

五个规范状态对应 **loading、ready、streamwait、dma、windowlife**，各 100 轮；windowupdate 是额外 pending copy 增强，不能用它抹去原规范“窗口更新后的进程”。已有 K7 100 轮证据可作历史对照，但其较少资源账不能替代本批完整 owner ledger。

storage 中 node_full 另测空节点导致 temp 创建失败且 epoch 不变；disk_full 允许空 temp 创建，但写失败后不 replace，等待 detached 排空再 sync，旧 probe 必须仍可读；unsealed_output 是 **Job compiler 输出**未 Seal 不对 creator 发布。普通工作区 Transient 的 Replace 合同不同，不应凭“未 seal”字面改写生产语义。原 K7 Job 权限全矩阵可复用已接受证据，但需明确其输入与当前 P 的差异影响；这六项并未重新覆盖整套权限。

## 4. 调度、失败与版本变化

按组串行运行 QEMU，避免与 K9/双编译器正式性能测量争 CPU 或造成 QMP/端口混淆。kernel 编译复用与 guest 状态复用是两件事：每个 mode 都新盘/新 QEMU，storage 的第二次启动才有意复用同盘。不能把一个 mode 的 warm cache/残留状态传给下一个 mode 以省时。

若 P 在本批中途变更，旧证据保持原输入身份，标记依赖过期；不能把不同 P 的五类轮数拼成一轮正式验收。由 reviewer 决定影响范围，但涉及调度、回收、FS/Power 等公共路径时，默认相关全组重新运行，仍可复用同一新 P 下已审核且输入相同的 observer kernel。测试代码修复也保留失败目录，不覆盖原始日志。

独立性能必须使用无 ledger 的 P 或已审核的轻量计时变体；资源 observer 对性能的扰动见 [有界性审计](K10-bounds-audit.md)。正常关机 DMA/temp 收尾应由 Power 专用场景在原样 P 上完成，本计划的 kill/同步/外部退出不能替代它。所有矩阵必需项通过后，再由独立 reviewer 汇总 K10 结论并提交；本计划不预先授予通过状态。
