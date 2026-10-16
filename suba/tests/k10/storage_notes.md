# K10 存储容量前置探索

这里只是测试准备，不是K10正式验收。入口 `tools/check_k10_storage.py` 复用精确校验的冻结生产内核，普通worker从真实初始盘 `/sys/worker` 经FS loader进入；可信U控制器从RAM启动，构建器还保留一份未作为普通spawn来源的worker副本。没有生产插桩，没有运行时host写盘，没有修改旧K4 fixture。

```sh
python3 tools/check_k10_storage.py \
  --compiler ../biomiya/build/source-cap64-p4-r3/e3.elf \
  --kernel-from build/k7-panic-production-r2 \
  --case node_full --out build/k10-storage-node_full-new
```

输出目录必须全新。每个case生成一块初始盘，完成同步和guest断言后由host停止QEMU、只读检查，然后对同一盘启动第二次。第二次不是重新格式化；真实boot serial必须1、2。这个流程不是Power正常关机测试，也不声称突然断电恢复。

## 旧fixture假设与覆盖

旧K4的stats数字4–11与当前 `abi/files.vt` 相同：source epoch、boot id、free blocks、free nodes、files、requests、block state、detached。因此这些输入原样复用，不编辑历史测试。按BootId分支的fixture要求新格式盘首次boot=1，工具从同步后superblock核对该前提。所有初始文件、worker以及目录都参与容量计算，不能拿旧RAM普通worker布局的剩余空间常量代入。

| case | 来宾断言与稳定状态变化 |
|---|---|
| node_full | 4096节点全占；普通文件/mkdir均NO_SPACE，删除n0000后复用节点（generation=2），replacement内容reused；每次启动还验证Transient创建NO_SPACE且source epoch不变，旧probe仍可读。节点保持全满，首轮多占1数据块。 |
| disk_full | 数据块全部占满；4次64KiB写入NO_SPACE，epoch和空文件size不变。增强：Transient空节点可创建，但写new仍NO_SPACE、size=0，调用方discard而不替换probe；最终容量及原有文件内容不变。 |
| disk_partial | 删除8块hole后，只剩8块可用；64KiB请求失败并回滚预留，epoch/size/空间不变，32KiB请求成功耗尽8块；unlink后全部归还，连续4轮，两次启动均执行。 |
| boundaries | offset1跨块写满64KiB，跨未映射页的read/write拒绝且不部分写，拒绝文件洞，逐字节验证65537字节内容及EOF；持久增加17块、1节点。 |
| unlink_reader | unlink立刻隐藏名字/目录条目，已打开reader仍读到旧14字节；最后close后释放1块1节点，中文保留名的list与重启可见性正确；最终增加目录+空文件两个节点。 |
| unsealed_output | 新的小范围Job场景：worker创建Transient输出，sync(false)并close但不seal；creator读与FS spawn都Denied，同时旧probe仍读old。取消worker后输出NotFound，Job收尾后空间回基线；不重做K7整套权限矩阵。 |

“未seal输出不发布”在这里特指Job输出。普通 `/work` Transient可以由owner关闭写句柄后经Replace原子发布，API并不要求先Seal，既有K7 publication正例就是此语义。容量不足的保存路径必须在写失败后discard，不能把空临时文件Replace过去；disk_full增强用例验证这个调用流程及旧文件保留。

## 实际空间账

控制器在收尾后验证动态页恢复、FS files/requests为0，显示前后free blocks/nodes。host读取已同步且QEMU已停止的盘：

- 逐个文件验证完整内容SHA-256、大小、generation，目录集合精确匹配预期变化；包含probe和系统worker及所有填充文件。
- 遍历所有文件FAT链，要求每个已分配数据块恰好归属一个文件，无跨文件共享、无分配孤块。
- 由实际FAT和节点表计算free blocks/nodes，与guest输出交叉核对；无Transient/Detached残留。
- 每次启动保留metadata.bin、原始guest记录和磁盘摘要；记录编译输入、冻结工具副本及摘要。

这里不是完整304项owner ledger，也不是生产延迟测试；生命周期完整账使用独立 `check_k10_lifecycle.py`。

## 遇到的测试问题

`build/k10-storage-disk_full-r2` 的新Transient失败写路径在unlink后立即SyncAll并报告绿色；host检查正确拒绝：节点18为flags=3、generation=3、size=0、名字temporary，已从namespace移除但异步回收尚未完成。该行为与 `kernel/fs/lifecycle.vt::cleanup_step` 的64项分步回收和 `operations.vt` 的SyncAll语义相符：SyncAll刷新元数据，不等价于等待所有Detached回收。

修正只在测试controller：有界等待 `STATS_FS_DETACHED==0`（5秒guest deadline）再SyncAll；若未回收返回错误13。保留r2失败，不能将其重写成通过或直接定性为生产泄漏。Power的正常关机排空协议由另一套独立测试验证。

## 探索身份和正式重跑

本组使用accepted r2原生产内核 SHA-256 `737f4cf3c24aa4cc85753694b3e7a00de595bf74bfbfb0a9a291fce07ea6c650`；没有混用观察内核。报告统一 `stage_acceptance=false`。详细冻结结果见 `storage_exploration.json`；不同报告各自保留当时实际wrapper输入摘要，不会因之后补等待逻辑而获得新证据。

K10正式矩阵需对K9/Power集成后的当前冻结候选重跑六个case。当前探索没有发现需要修改生产的BUG；尚不能据此宣告当前Power候选已通过。
