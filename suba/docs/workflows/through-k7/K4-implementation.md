# K4 存储实现与复现

2026-10-16。本文描述实现，不替代独立验收报告。源码基于 K3 提交 `6162887`，使用 C64 编译器 SHA256 `22d2c81fd0dbfc6de6b3b13fb2f485b1c64913849d9e59eeabe8c2757d27ebf4`。

## 状态和所有权

`kernel/device/virtio.vt` 拥有 split queue 的 head 身份及生产/消费序号；`block.vt` 拥有一个永久 DMA bounce 和唯一在途请求；`hub.vt` 把真实 PLIC 来源交给驱动。FS 不直接读 MMIO 或等待设备。运行期 `entry::schedule` 在每次有限工作片之前服务 PLIC，然后推进 FS、进程请求和回收。设备错误/超时使可信内核停机；磁盘满、坏用户地址、无权限等属于可返回失败。

`kernel/fs` 是单一模块，分文件按职责组织，而非多个可独立改写元数据的管理器：

| 文件 | 所有权/职责 |
|---|---|
| `state`、`mount` | 元数据 RAM 权威副本、启动校验、递增 boot serial 后 FLUSH |
| `path`、`codec`、`mount_check` | 纯路径和磁盘字节校验，不调度、不驱动 I/O |
| `namespace`、`operations` | 分片解析真实目录；权限沿真实父链判断；创建、删除和枚举 |
| `files`、`lifecycle` | File 引用、独占 writer/共享 reader、cwd pin、Transient 与 detached 回收 |
| `requests` | 每进程一个带 generation 的排队请求；复制路径，不保留 U 指针 |
| `transfer` | ≤64KiB staging、全部块预留、4KiB DMA、提交或预提交回滚 |
| `worker` | 有界推进、脏元数据编码、FLUSH、关闭与只读资源账本 |

`dispatch_file` 保留原用户地址及 K3 请求 token；完整范围在排队前校验。FS 的 Input/Output 只借出内核 staging 的至多 4KiB 视图，由 dispatch 在仍可交付时复制并确认。不向设备传 U 页，不跨等待保留调用栈切片。

写入在第一个 DMA 之前完整接收用户数据和预留所有新增块；NoSpace 或此时取消均撤销本次预留。第一个 DMA 已发出后取消只撤销向用户交付，FS 继续完成已接受事务，最后释放请求持有的 File pin。进程 Tail 等待其 FS 请求、Transient 和归属回收完成后才发布退出。因此 kill 成功不等于 DMA 已完成，collect 看到退出时才可以比较回收基线。

unlink 和 replace 立即改变名字空间。旧 reader 仍绑定旧节点；最后一个 reader 关闭后，有限清理步释放旧块和节点。cwd pin 阻止目录被删除；spawn 在进入 ELF 准备前取得真实 cwd pin，失败/取消释放，成功转交子进程。初始 cwd 为 `/work`。

## 当前功能边界

固定 256MiB raw 盘，FS 区间沿 ABI；4096 节点、单文件 ≤16MiB、每次读写 ≤64KiB、名字 ≤63 UTF-8 字节、路径 ≤255 字节、目录深度 ≤16。一个 FS worker、64 个 File 对象、每进程一个待完成请求，不实现缓存替换或并行磁盘队列。`/sys` 只读、`/work` 可写；`/jobs` 的权限和冻结由 K7 接续。

已实现 open/read_at/write_at/stat/sync/list/mkdir/unlink/replace/sync_all，Transient 只有其 owner 能访问，SEAL 成功以 FLUSH 完成为界。没有隐式文件位置、洞、truncate 或突然断电恢复承诺。正常关闭完成全局 metadata/FLUSH 后再退出 QEMU；测试的新启动挂载真实同一 raw 盘。

用户进程仍从固定 RAM fixture 的 `/boot/N` 加载，用于把存储验收与加载 provider 分开。K7 接真实文件输入时复用当前 ELF/页表/loader，不新增第二套加载器。当前 K4 不声称已具备桌面编辑器、系统内编译或磁盘启动部署。

## 实际复现

在 suba 根目录运行，每次指定尚不存在的输出目录：

```sh
python3 tools/check_k4.py --compiler ../biomiya/build/source-cap64-p4-r3/e3.elf --case filesystem --out build/k4-local-filesystem
python3 tools/check_k4.py --compiler ../biomiya/build/source-cap64-p4-r3/e3.elf --case boundaries --out build/k4-local-boundaries --kernel-from build/k4-local-filesystem
```

同一生产内核的 `disk_full`、`disk_partial`、`node_full`、`cwd`、`unlink_reader` 可复用已编译快照；复用前逐项核对编译器、所有 kernel 输入和 ELF 哈希。不同取消控制改变测试快照，不能借用普通内核。`cancel_pre`、`cancel_reserve`、`cancel_dma` 各观察真实阶段后由 U 父进程执行 kill_child；`cancel_no_irq` 是关闭 SEIE 的必要负控。控制只存在于忽略的构建副本，不修改正式生产源码或 ELF。

每次报告保留初始盘、输入哈希、编译/运行命令和两次启动日志；主脚本只在全部断言成立时记录 passed。ABI selector 6–11 分别报告可分配块/节点、File、FS 请求、块设备状态和 detached 节点；取消用例还比较物理页基线。全局只读账本用于核查资源归属，不能被用户修改。

纯格式/元数据测试与实际设备证据各自独立：`check_mkfs.py`、`check_fs_metadata.py` 不替代真实坏盘启动；实际故障由 `check_k4_faults.py` 验证。共同 transport 的冻结和独立报告见相邻 `K4-transport-*` 文件。
