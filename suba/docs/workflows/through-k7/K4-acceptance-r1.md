# K4-r1 独立验收

结论：**通过 K4 功能门槛**。验收者 `/root/k4_review` 未参与生产实现；本轮只审查、添加独立测试和形成验收记录，无自行提交。2026-10-16。依据原 `design/IMPLEMENTATION.md` K4 阶段行、`design/CONTRACTS.md` 与 `CODE_STYLE.md`，不把 K10 整体验收矩阵或后续 K7 能力提前算作完成。

候选 `K4-candidate-r1.json` SHA256 为 `767ff03e757cb707b7ae81ff05fb3b5afe652af7595db760901e80c9491d4105`。84 个 owned、37 个 inputs 和 C64 编译器摘要均匹配，开始与结束各复核一次。作者13项文件系统记录的报告、实际编译副本、ELF、两次启动日志均核验。DELIVERY 是明确排除的协调日志；K5/K7 文件不属于此次判定。

## 实际独立验证

以下命令在 suba 根目录执行。输出目录首次运行时不存在，具体 argv、快照摘要及日志索引见同名 JSON 和各目录的 `verification.json`。

```sh
python3 tools/check_k4.py --compiler ../biomiya/build/source-cap64-p4-r3/e3.elf --case filesystem --out build/k4-review-filesystem-r1
python3 tools/check_k4.py --compiler ../biomiya/build/source-cap64-p4-r3/e3.elf --case cancel_dma --out build/k4-review-cancel_dma-r1 --kernel-from build/k4-cancel-dma-r5
python3 tools/check_k4.py --compiler ../biomiya/build/source-cap64-p4-r3/e3.elf --case cancel_no_irq --out build/k4-review-cancel_no_irq-r1 --kernel-from build/k4-cancel-no-irq-r3
python3 tools/check_k4_faults.py --kernel-from build/k4-filesystem-r5 --out build/k4-review-faults-r1
```

另以 `tools/check_k4.py` 实际运行 `transient_owner`、`cwd_identity`、`unlink_reader`、`disk_partial`，输出分别为 `build/k4-review-<case>-r1`，均使用上述编译器和 `--kernel-from build/k4-filesystem-r5`。

| 范围 | 独立结果与区分力 |
|---|---|
| 全新编译与实际持久 FS | 新编译验收内核与作者 filesystem-r5 ELF **全文件相同**，SHA256 `87451fecfd59ed3df7f64f2a6e15e19448b1990ec7ed2274eb724ca14e405127`。两次实际 guest 启动完成创建、写入、同步、替换、旧读者、UTF-8 名字、权限与恢复；第二次从同一 raw 盘读回完整新内容。另用独立 struct 解码读取实际 FAT/节点/链，核对完整文件字节、旧名/临时名消失及所有存活节点 flags=0。 |
| 真实 U IRQ 与取消 | 每次启动100轮，两个启动共200轮。目标是第二个真实数据 DMA，U 父进程观察阶段后执行 kill；仅在下次返回 U 前恢复 PLIC，中断完成必须等新的真实 U external trap 后才能消费。两次实测 external trap 数397/398；每轮物理页、FAT可用块、节点、File、FS请求、block idle、detached 回基线。关闭 SEIE 的同路径负控在首次取消后由原生产 deadline 触发 panic73，没有回收/成功标记。 |
| 名字与 pin 修复 | transient_owner 两启动拒绝另一进程 open/unlink/replace，创建者仍逐字节读到原内容且退出清理；cwd_identity 两启动在删除启动字符串中的 temporary 后仍能默认继承真实目录并相对创建。旧版精确失败175/205的记录保留，修复不靠降低预期。 |
| 旧读者和部分预留 | unlink_reader 两启动验证名字立即消失、旧句柄仍读完整内容、最后close归还块/节点、LIST 的96B记录及中文名。disk_partial 每启动4轮：只留8块，请求16块确实预留部分再失败，size和epoch不变、8块全归还，再写8块成功；新启动重复成立。 |
| 实际坏盘与 I/O 失败 | 独立重跑11例：正常控制、4类实际元数据损坏、挂载读/启动序号写/FLUSH EIO、运行期数据写/元数据写/驱动读 EIO。要求对应 panic70/71，运行期要求先 mounted，禁止成功标记；QEMU命令失败或宿主超时不能单独通过。额外核验 root 的最终 r5 专门 FileRead 健康/193块EIO证据，其 fixture 无前置写。 |
| 既有保护与资源合同 | 独立 `tests/k4/independent_fs/check.py` 运行 memory、streams、spawn_invalid、tree、orphan_tree、blocked_writer。保留原断言，只将旧fixture的相对RAM路径改为显式 `/boot/1`、cwd从虚拟`/boot`改为真实`/work`。新kernel上128轮alloc/free、跨页、背压/EOF、继承失败、父子/Job取消均通过，最终回到统一页基线。 |
| 独立新增反例 | protection 让子进程访问 virtio/PLIC 的 S-only alias、kernel、栈guard、只读参数页及执行S CSR，逐项核对13/15/2硬件原因，父进程哨兵不变，6次故障均完整回收。file_capacity 区分父Child+63File的本地句柄耗尽与子第64File的全局对象耗尽；新节点失败撤回、释放后重用、transient退出清理与stale handle拒绝均通过。 |

8项独立回归记录在 `build/k4-independent-*-r1`。其中 `file_capacity` 的输出目录用 `file-capacity` 拼写；冻结脚本新增这一分支前已执行其余7例，其他分支及实际编译输入未改变，原始副本逐项验证。测试没有修改生产源码或ELF。

## 身份复用与未重复范围

`--kernel-from` 实际核对编译器、所有实际编译的 kernel 输入（含明确测试观测点）及ELF摘要；没有让新fixture搭配身份不明的旧kernel。新编译的 filesystem 内核含测试用正常关机观测点，并非无插桩正式 ELF；其余生产路径保持候选原文。

共同 transport r1 的8 owned+2 inputs仍完全匹配，沿用原独立验收，不重复65,544 IRQ回绕测试，也不将它扩展为完整FS结论。作者最终版本上的 boundaries、disk_full、node_full 记录和源码已核查：64KiB跨17块及跨未映射页拒绝、真实满盘、4096节点满/释放/代数重用都有明确断言和正常重启；没有机械重跑所有已充分覆盖场景。

作者 pre-copy 与 Reserve 取消各100轮×两次启动使用修复前4个文件，不能称为最新ELF。逐项diff确认差异仅是 transient owner检查与空cwd继承：这些fixture使用自己的transient及显式`/work`，不走新增继承分支；新增权限谓词对owner返回true，旧代码已经检查同一owner。块预留/回滚、FS request/worker、DMA和Tail路径均未改，故接受这些结果对本候选的有限适用性。新版较大的 prepare_spawn frame另由最终DMA和独立spawn/tree测试覆盖。旧完成屏蔽超时快照同样只作旧版本证据；新版SEIE负控已实际命中未改动的生产deadline。

root 的15项mkfs和128项纯codec/mount-check报告摘要已核对，限定为格式/纯校验器证据；实际坏盘门槛由独立QEMU测试补足。旧 `data_read_eio` 只定位到驱动Read，不能单独推出用户FileRead，最终专用只读fixture补齐此歧义。

## 审查与成本

新增状态归FS、block与对象所有者管理；dispatch只持请求token和未经解引用的用户地址，完整UserRange在排队前验证，复制时复核存活资格。单串行worker保证元数据互斥；各步按最多64表项或4KiB搬运推进。写入先收齐staging并预留全部新增块，提交前取消/NoSpace撤回，提交后只撤销交付并完成已接受事务。设备永远只访问永久内核DMA；退出Tail等待自身存储资源，不把“用户页已释放”等同“设备已结束”。

审查曾找出的两项生产BUG已修复并有旧失败、新成功反例：命名空间变更遗漏 transient owner；默认cwd误重新解析显示字符串。它们与测试/设备模型难点分别记录在engineering notes，未抹去失败。失败create可能保守推进source_epoch仍列非阻断改进项：会触发多余Busy，不会发布错误快照；本次不宣称已修。

验收ELF为1,220,640 B，RX为1,210,836 B，BSS为12,587,456 B；50 VT、3 S0是完整kernel清单口径，不隐去运行支持。独立读取机器码frame并按模块解析直接调用图：最大单帧10,368 B位于 `dispatch::prepare_spawn`，start可达链31,680 B、trap链31,440 B、panic链1,024 B，无VT递归；固定桥/S0开销另计，在128KiB栈预算内。此为本候选保守调用链账，不是延迟证明。部分多语句行、长穷尽match仍值得教学整理，不影响本轮所有权与有界性判定。

## 通过边界

没有剩余K4功能阻断。永久DMA/元数据存储独立计账，测试证明正常设备下的应用回收；失联/错误设备按合同停机，不算“故障设备仍完整回收”。通过正常FLUSH/重启，不承诺突然断电恢复。

测试关机在作业排空后调用FS shutdown_step；当前尚无完整电源管理UI/拒绝新作业的全系统关机入口。当前 `/boot/N` 仍是RAM fixture provider，`/jobs`冻结权限、持久ELF加载、桌面/编辑/编译闭环属于K5/K7。5ms片目标、完整连续S驻留/IRQ延迟及两个编译任务背景响应未被本次验收证明。K4通过不等于K7或原生自举完成。
