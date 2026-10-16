# K3-r1 独立验收

结论：**K3 功能门槛通过**，允许解除 K4/K5 的 K3 依赖。没有发现必须返工的功能阻断。**性能目标未全面达到；连续 S 驻留、IRQ 服务延迟和两编译任务背景尚未测量**，不包含在通过声明内。

验收者 `/root/ram_acceptance` 未参与本轮生产实现及 root 的早期草稿；仅审查、运行独立测试和编写本验收记录。未修改生产文件、冻结候选或作者原始证据，未提交。判断依据是原 `design/IMPLEMENTATION.md` K3 行、`design/CONTRACTS.md` 与 `CODE_STYLE.md`，而非仅依作者报告。

## 身份与证据边界

候选 `K3-candidate-r1.json` SHA256 为 `49c0d6c1639e5782bccef6b283018fceb3c724c8ac0e2eb0e9f401d5725f4a44`。51 owned 文件和 19 个静态 inputs 均精确匹配。第 20 项 `DELIVERY.md` 是 root 独占调度日志：当前仅修改 K3 派发/状态行并追加候选摘要；冻结副本 `build/k3-coordinator-inputs/DELIVERY-frozen.md` SHA256 `2b5188e7b4a27285f09c8ec80c0f4269dbbf1ca285854958241b7dc250959f41` 精确匹配候选，差异已检查，不改变功能合同。不能称当前 71 个文件全部未变。

编译器仍为旧 E3 `049c6e094ccd044fba3b5d357583013b77f0e8e9a98d431ad919e02b0cda2144`；没有使用 C64。正式 ELF `build/k3-production-r2/build/kernel.elf` SHA256 `d186379f2df7717d0a42628df03fcd001f8168a211f07dc5c9f07a290e70a80c` 已核验。作者索引中 51 份历史记录及其 serial 摘要均匹配；历史失败和中间版本仍是历史证据，没有当作当前候选全部重跑或二进制相同。

独立测试保留于 `build/k3-independent-r1`、`build/k3-independent-extra-r1/domain`。每次真实编译、QEMU argv、输入摘要、串口和断言结果见各自 `verification.json`；本文件配套 JSON 给出身份索引。测试副本与候选生产文件逐项核对，差异仅为已审查的测试终点、故障注入或负控；未更改实际容量以缩短测试。

## 独立运行与区分力

实际执行 `python3 build/k3-independent-r1/run_suite.py`，串行调用当前冻结工具：

```sh
python3 tools/check_k3.py --compiler ../biomiya/build/layout-p4-r1/e3.elf \
  --out build/k3-independent-r1/<case>-<mutation> --case <case> --mutation <mutation>
```

完成 18 项：15 个正向/故障恢复场景和 3 个负控，全部得到预期结果。

| 范围 | 当前候选独立运行 | 核对内容 |
|---|---|---|
| U syscall 与内存 | smoke、memory、rollback、allocation_failure/allocation-1 | 清零、128 次完整 alloc/free 基线、部分/重复 free 拒绝、跨 2 MiB 页表、真实 96 MiB 配额失败回滚、空页表与部分分配回收 |
| 流与继承 | streams、spawn、spawn_invalid、handles | 64 KiB 环背压、partial、有效/无效跨页和只读 copyout、EOF/BrokenStream、argv/cwd、显式 stdout/stderr、部分继承失败无残存 writer、64 句柄容量/代数 |
| 等待与树 | waits/late-token、tree、orphan_tree、process_limit、blocked_writer/late-token | 16 watch、先验证所有条目、deadline、重复 kill/stale Child、Job 取消孙进程、直接父退出、关闭 Child 不解除树边、16 进程容量、取消写不改变缓存且最终 EOF |
| 两个所有权窗口 | cancel_prepare/cancel-reservation、cancel_prepare/cancel-install | 未绑定退出记录保留和已绑定但未装入句柄的 Child 引用分别被取消；要求窗口标记、孩子退出、EOF 和统一资源基线 |
| 负控 | memory/omit-prune、waits/omit-token-revocation、streams/prefix-only-usercopy | 分别精确得到用户退出 15、panic 23、panic 22；证明测试能发现缺少剪空表、取消后仍可交付、只检查首用户页，不能只靠“启动成功”通过 |

另实际执行 `python3 build/k3-independent-extra-r1/run.py domain`：父 Job token 与子 stdout token 刻意同为 257；子使用它尝试 JobEnd/kill 必须 Denied，使用父未继承的 read/Child token 必须 BadHandle，随后合法 stdout 写仍成功。父能再次加入同一 Job，证明子未借相同数字结束父 Job；再取消、collect、EOF、完整回收。该探针通过，不只是重复作者成功用例。

独立探针已归档为 `tests/k3/independent_domain.vt` 和 `tests/k3/independent_domain.py`。归档入口生成的 domain/worker VT 已与上述实际运行副本逐字节核对；入口本身是整理后的复现包装，未另算一次运行。复现：

```sh
python3 tests/k3/independent_domain.py \
  --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/k3-independent-domain-replay
```

探索目录里准备过的 32 次重复继承失败变体没有执行，未计入验收。没有机械重跑作者全部 51 份历史记录。

## 审查判断

- objects 使用进程身份、槽代数、类型和 rights 共同裁决；代数耗尽不回绕。request 分离清理所有权与交付资格，Dying 立即失去交付资格，之后仍能释放请求保留的资源。单串行调度器以 level 状态、deadline 和同一 token 决定终结，没有检查后并发登记的丢唤醒窗口。
- spawn 从用户参数页分片快照后验证，普通路径与启动路径共享 ELF decoder/逐页 loader。保留记录、子进程、父 Child 句柄、显式继承端点分别有明确转移点；两个中途取消窗口经过实际验证。没有普通应用可指定的 privileged 参数。
- 子树取消和回收按有限状态推进，不递归。Child 关闭只放弃收集权，父子生命周期仍在；父 Tail 与 JobDone 等后代完成。页、句柄、stream/children/job 对象归统一 owner 释放，统一终点同时检查对象静默及页基线，而非只看进程列表消失。
- usercopy 保持 SUM=0，先验证完整页范围/权限，再经物理映射搬运；阻塞单线程的用户映射不会在请求推进中被自身另一个 syscall 修改。动态页范围只允许完整精确 free，页账本孔位复用、live 配额、空表计数与逐步 rollback 能互相对应。
- 实现按所有者分层，dispatch 协调且叶所有者不回调。固定容量和较大 buffer 可定位，不引入另一套通用异步/资源框架。多文件同 module 的 import 约束与若干嵌套 match 已说明，未发现需要为 K3 门槛重写结构的阻断。

## 成本与未完成事项

验收者独立读取正式 ELF 的 program headers、源清单和文件字节数：30 VT 共 4772 行/217442 B，2 S0 共 261 行/5181 B；ELF 696336 B，RX 687844 B，BSS 11336176 B，PT_LOAD 跨度 12028416 B，均与报告一致。固定页账本 6 MiB、索引 1 MiB、allocator 1.5 MiB、stream ring 2 MiB 已包含在 BSS，不重复相加。最大单函数帧 9344 B 来自已核验输入/编译器的构建计数，**不是最深调用链栈界证明**；本轮没有另行重建无插桩正式 ELF 或形式化证明整条调用链。

当前独立轮次的有计时场景最大 dispatch 片范围为 3.2755–5.1778 ms，仍有超过 5 ms 的场景；具体数值完整保留在 JSON 与原始日志，不筛选最好值。dispatch.call/step 的单片计时不能推出连续 SIE-off/S 驻留上界。K4 必须实际服务外部 IRQ 并测 pending 到处理的延迟；已提交 DMA/FS 的引用还须加入现有 Tail 门，设备故障与应用回收分开验收。K7 两编译任务背景交互目标尚未验证。

当前 `/boot/0..7` 是真实 RAM 字节 provider，不是持久 FS；Job 的 `freeze_inputs` 对合法对象返回 Unsupported，未假装完成冻结。K4/K7 必须兑现磁盘提供者、冻结权限、在途 I/O 收尾及构建闭环。K3 通过不等于内核原生编译器自举、窗口桌面、FS 或整个 K7 已通过。
