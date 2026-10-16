# 推进至 K10

用户授权：排查并修复 panic，持续完成 K10。沿用每个大阶段独立验收后提交及记录阻塞的要求。
K1 磁盘部署仍延期；宿主仅按字节搬运 guest 已生成的内核 ELF。

## 输入与依赖

起点：suba `49b2213`，biomiya `65cb036d1279975dd01d8aee248c6cf0612c8b92`。
K7-r3 已独立验收通过（K7-acceptance-r3）；历史判定和样本保留在 through-k7 与 build。
图：`K7-r3 → K8 → K9 → K10`。无并行生产写入依赖；提前开展的下游工作仅是探索。

| 节点 | 作者 / 独立验收者 | 写入范围 | 门槛 | 当前状态 |
|---|---|---|---|---|
| K7-r3 panic | /root/k5_finish；集成 /root / /root/k4_review | kernel、必要 ABI、kernel K7 测试及对应工具；全局记录由 root | 归类失败或修复对应缺陷；有区分力回归；复核 K7 既有功能与持久化 | 已独立验收，提交 08a4d07 |
| K8 | /root / /root/k4_review | tests/k8、tools/check_k8*、必要原生构建支持和记录 | 原生 C0→C1→C2→C3 全文件相等、源码行为扰动、host 同输入对照、回收 | r2 已独立验收，提交 9d948fd |
| K9 | /root / /root/k4_review | tests/k9、原生 kernel/S0 清单、按字节搬运工具和记录 | guest 分别修改 VT/S0→完整 ELF→sync→host 同输入对照→搬运启动见变化→应用编译 | r1 候选冻结；native-r2进行中，GUI/运输已通过 |
| K10 | /root；必要内核修复 /root/k5_finish / /root/k4_review | 全局测试、必要修复、docs/reference、读者路线、成本账 | IMPLEMENTATION §4 全部必需项，100 轮各类终止、实测成本、清洁复现与边界 | 等待 K9 |

合同依据 design/IMPLEMENTATION.md、design/CONTRACTS.md、CODE_STYLE.md。候选须冻结源码/产物哈希及实际依赖；
验收者没有参与上述候选生产实现，记录实际命令、判定和范围。新候选改变依赖时按影响复核，不静默沿用旧通过。
性能按原合同作为测量目标报告；不得把缺失测量或功能失败改成通过。规模计手写 VT/S0、运行支持、测试/工具，生成数据单列。

## 本轮记录

- 已恢复实际代理 /root/k5_finish 与 /root/k4_review；前者实现 panic 节点，后者独立调查/验收，不修改生产。
- 原始偶发 panic 与另一次 job DMA 失败继续保留，不因后续成功而标记修复。

- 前置探索 /root/k10_inventory：仅 tests/k10、tools/check_k10_lifecycle.py 及盘点文档；当前 FS loader 迁移与100轮fixture，不改生产。正式候选与验收仍等待K9。
- root 新增 boot/ram、ram_launch、K8/K9 测试入口为提前探索；不能据文件存在认定下游完成。

K8-r2：正式全链 `build/k8-native-r1/verification.json` passed=true，guest 1349.04秒；
独立验收见 K8-acceptance-r2.md/json。C0/C1/C2/C3完整ELF相同，源码扰动退出2→7，
Linux同输入c1/hello/mutant逐字节相同，独立短链另编译返回73的程序。
该节点不改变生产编译器或内核，不包含正常关机与K9/K10验收。

K9 当前：候选 K9-candidate-r1，正式原生链 build/k9-native-r2；首轮 r1因测试日志
在Job捕获epoch后创建而正确收到Busy，修正仅移动日志创建顺序，K8旧证据绑定原哈希不改写。
build/k9-manifest-r1、build/k9-transport-r1已通过；独立固定boot阴性、复制及解析竞态
在build/k9-independent-pre与build/k9-independent-r1。K9未整体接受，K10仍只提前探索。
