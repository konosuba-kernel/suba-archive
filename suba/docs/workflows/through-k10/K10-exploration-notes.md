# K10 测试前置探索记录

本记录不是阶段验收。生产基线固定取 `build/k7-system-r5` 的校验过源码，避免与 K7 panic 修复同时修改或混编。只读测试 observer 追加在输出快照 `dispatch_call.vt` 中；生产树未变。工具为 `tools/check_k10_lifecycle.py`，边界见 `tests/k10/README.md`。

## 已观察的问题

| 记录 | 观察及处理 | 对语言/架构的参考 |
|---|---|---|
| `build/k10-user-preflight-r1` | 14源、2S0的isolation控制器编译成功；只证明编译，非运行结果。 | 共享worker角色使每个场景无需另一个内核build；仍按模块拆出memory/streams/handles，不塞入生产。 |
| `build/k10-explore-ready-r1` | 100轮Ready状态观察、普通FS装载、kill/collect/stale token与现有账本通过。free pages=124606；streams/children/jobs/FS files/requests/block/detached均0；free blocks48672、free nodes4091。 | 不能只靠固定sleep推测调度状态；只读真实状态查询让测试更有区分力。仍未覆盖完整handle/wait/surface账。 |
| `build/k10-explore-streamwait-r1` | fixture退出2；测试错误要求stream write每次恰好4096字节。生产按有界片返回短写是合同允许行为。测试改为0<n≤请求并累计，不改生产。后续使用r2新目录。 | 直接使用Reply需每个调用点正确处理短写。可讨论标准库显式write_all/read_exact辅助，但低层测试仍应保留短写断言。 |
| `build/k10-explore-isolation-r1` | fixture遗漏case循环的i递增，持续重跑第一个kernel-read反例。发现后SIGINT停止，保存原始重复fault日志、false报告和未完成范围；不是panic或内核回收失败。补自增后使用r2新目录。 | 手写while游标易漏进度；代码规约可要求循环更新点清晰、测试控制器也有总期限。是否引入有限range迭代语法应另提语言设计，不为本测试扩张语言。 |
| `build/k10-explore-streamwait-r2` | 100轮通过，80.994s。逐轮free pages124603、free blocks48671、free nodes4091；其余已观察活数归0且无漂移。 | 真实Blocked+Write观察与满流数据保持一起证明取消发生在流等待中。 |
| `build/k10-explore-window-r1` | FS迁移后普通100轮通过，72.000s。逐轮free pages124626、free blocks48678、free nodes4091；其余已观察活数归0且无漂移。 | 旧代数/布局拒绝、像素copy、kill/collect已在当前FS loader路径重新执行；不包含两处K5特定竞态插桩。 |
| `build/k10-explore-isolation-r2` | 9个case通过，12.077s。串口恰好7次硬件故障隔离；除零exit101、私有写入正常exit0。每次case后victim旧计数先排空，再要求新计数与私有哨兵正确。 | 同一worker ELF的PRIVATE虚拟地址相同，各地址空间的内容仍独立；不把地址数值相同误认为共享物理页。 |
| `build/k10-explore-identity-r1` | 8.904s通过：普通FS-loaded child分别运行memory、streams、handles，新增overflow/错误kill权利/超长wait断言；父伪Child拒绝及最终账恢复。 | 这不是全部K3身份/迟到完成矩阵，只覆盖README列明的核心回归。 |
| `build/k10-explore-queue-r1` | 15.400s通过：100个真实QMP键边缘，普通FS-loaded窗口队列溢出；InputReset/Focus/CloseRequested顺序、陈旧布局/焦点/重复序号拒绝、退出恢复。 | 不是100轮队列场景，仅1轮含100个边缘；不代替原始驱动队列溢出测试。 |

原始失败目录不覆盖；后继成功不能使这些记录变成通过。阶段性成功报告含 `stage_acceptance=false`，正式K10需绑定K9后的候选重新执行。

上述成功运行共享观察版内核SHA256 `2cad5a6720027fae2a42ff4f6fa1a52aaaf3335390d806f33b19e9d9fe6316ba`。用户fixture各自冻结；期间更正了其他角色和测试错误，因此不能声称所有运行的用户ELF相同。逐项实际源码身份在对应 `compiled_inputs`，原始副本同目录保留。

汇总摘要见 `K10-exploration-results.json`。工具最后补上依赖Python脚本复制到 `tool_snapshot/`，不改变测试/guest动作；上述旧探索目录不追补伪装成执行时已保存的脚本。正式重跑使用此增强后的入口。
