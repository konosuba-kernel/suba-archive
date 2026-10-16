# 阅读 suba：沿行为追踪所有权

这是一份源码路线。各阶段完成状态见工作流记录；路径存在不等于其所有场景已经验收。
建议先看 CODE_STYLE.md 中的所有者、错误返回和有界步骤约定，再按下面四条实际路径阅读。

## 创建应用直到第一次进入用户态

从 `user/libsuba/services.vt::spawn` 的固定记录开始，进入
`kernel/dispatch_call.vt::call_inner`，再到 `dispatch_spawn.vt`、`image_reads.vt`。
这里把路径、参数、流能力和 Child 身份转为一个可取消的装载请求；普通应用来自 FS。
接着阅读 `abi/image.vt::inspect` 的纯 ELF 计划，再看 `loader.vt`、`space.vt`、
`process.vt` 如何分配、清零、映射与发布。最后由 `entry.vt::schedule` 选择进程，
`trap.s0` 恢复寄存器并 sret。区分“ELF 文件字节”“内存跨度”“实际分配的页”。

## 文件读取怎样等待中断再恢复

`user/libsuba/files.vt::read_at` → `kernel/dispatch_file.vt` → `request.vt`。
请求保存身份和边界，不能保留未经检查的用户指针。`fs/requests.vt` 排队，
`fs/worker.vt` 与 `fs/transfer.vt` 每次推进一小步；`device/block.vt` 发布 DMA，
`device/hub.vt` 从 PLIC 取得中断，`device/virtio.vt` 校验 used ring。
完成后沿请求令牌检查回到 copyout 与进程恢复。等待使这个进程暂停，不能让整个内核
忙等设备；通知也不是完成本身，必须核对设备状态和队列。

## 错误或强杀怎样最终回收

用户 fault 从 `trap.s0` → `entry.vt::handle_trap` → `process.vt::capture`；
主动 kill 从 `dispatch_call.vt::kill_child` 验证 Child 权限后汇合到 terminate。
重点读 `dispatch.vt` 的 Cleanup 状态、`children.vt`、`jobs.vt`、`request.vt`：
先撤销交付，再关闭句柄和取消子树，等待真实设备引用排空，分片回收页，最后保留退出记录
直到父进程 collect。`window_surface.vt` 和 `fs/lifecycle.vt` 分别展示表面与临时文件的尾部回收。
进程不再出现在可运行队列，只是回收开始；完整账本恢复才是回收结束。

## 编辑源码到部署新内核

`user/edit/actions.vt` 驱动保存/构建/运行。`user/build/main.vt` 是工作流程，
`manifest.vt` 做纯清单规划，`snapshot.vt` 复制并冻结输入，`compiler_streams.vt` 同时排空
两条输出流，`publish.vt` 验证和发布。编译器源仍维护在相邻 biomiya 仓库；suba 不复制
第二个可分叉的编译器实现。`biomiya/compiler/runtime/host_suba.vt` 只是环境适配。

内核部署沿 `tools/ram_launch.py` → `boot/ram.vt` → `kernel/entry.vt`：宿主验证完整
产物身份并复制；固定引导校验范围和构造 BootInfo；内核接管页表与设备。源码编译、原生
产物验证、宿主搬运、实际启动是四份不同证据，不能相互替代。

Linux 更庞大的页缓存、设备模型、并发、多核、驱动和兼容层可以在这些具体机制之上继续阅读。
这里的小实现提供入口，不把省略的 Linux 能力说成已经支持。
