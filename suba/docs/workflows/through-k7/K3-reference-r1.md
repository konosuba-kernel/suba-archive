# K3 语言使用者接口（候选）

本版基于 S-next 冻结 E3 与 suba K2，用户程序使用 `suba-user` profile，入口返回 `u32`，通过 `user/libsuba` 调用内核。此文记录当前实现，不将 K4 文件系统、K5 窗口或 K7 编译器适配视为已交付。

## 返回与身份

`syscall::Reply {status,value}` 使用 `abi/contract.vt` 的状态码。失败时不得解释 value 为有效句柄或地址。句柄是当前进程的 64 槽表中的代数 token；close 立即使旧 token 失效。相同数字在另一进程中没有身份转移意义。操作还检查对象类型与 rights；裸进程编号不具备 kill/collect 权限。

一次同步调用最多形成一个内核请求；内核阻塞调用者，其余进程继续运行。kill 先使进程不可交付，再取消请求和关闭资源；用户指针或栈不由请求保留为内核指针。

## 页与流

`services::allocate_pages(n)` 分配清零、连续虚拟地址的页范围；物理页不要求连续。单次上限 16384 页，进程 96 MiB 配额还包括私有页表/装载页及外部所有者计账页。失败回滚已分配页和空页表。`free_pages(base,n)` 只接受此前分配的精确完整范围；部分 free、重复 free、内核地址均拒绝。

`services::streams()` 返回 read/write 两端；环容量 64 KiB。read/write 的用户范围最多 64 KiB，整个范围先验证，实际一次最多传输 2 KiB（两次复制合计最多 4 KiB），调用者必须处理 partial。零长度返回零。最后 writer 关闭后，reader 先读完缓存，再得到 OK/0 EOF；最后 reader 关闭后，writer 得到 BrokenStream。NONBLOCK 遇当前无法推进返回 WouldBlock，亦适用于调用入队后 readiness 变化的情况。

## 等待、进程与作业

`services::wait(watches,deadline,nonblock)` 最多 16 个 watch。返回 ready 位图，所有 watch 均先验证。deadline 为固定 QEMU 10 MHz 时钟的绝对 ticks；零表示无截止，OK/0 表示到期。readable/writable/exit/hangup 为 level 条件，不消费流字节或退出记录。零 watch 可用于仅等待 deadline。

`services::spawn(path,argv_page,stdout,stderr,job)` 使用固定 4096 B 参数页，构造器见 `argument_builder`。argv ≤64 个显式长度字节串，cwd ≤255 B。空 cwd 继承父进程；只有显式 stdout/stderr writer 被保留并安装到孩子，其他句柄均不继承。用户参数页中的伪造 stdout/stderr 数字会被覆盖。只读参数页位于 `ARGUMENT_BASE`，`arguments` 提供读取接口。

当前字节来源仅为启动时已保留 RAM 中的 `/boot/0`…`/boot/7` fixture；cwd 只接受 `/`、`/boot`。它不读宿主路径，不是磁盘文件系统。K4 将替换字节 provider，保留同一生产 ELF 校验器和逐页 loader。不存在普通 spawn 的 privileged 参数。

spawn 成功返回父进程独占 Child 句柄。kill 可重复终止同一个尚未 collect 的孩子；collect 只在全部用户页、句柄及子树清理完成后返回固定退出记录，并消费 Child 句柄。关闭 Child 句柄只放弃收集权，父子生命周期边仍存在。父进程退出会逐层取消所有后代；清理是有界状态推进，不使用内核递归。

Job 支持 create/end、子进程计数与完成等待。JobEnd 取消其孩子及整个后代树；JobDone 等待树清理完成。`freeze_inputs` 当前对合法 Job 返回 Unsupported，冻结树权限与 FS 事务留待 K4/K7；没有以空成功代替。

## 当前测量边界

stats 提供空闲页、时钟、最大 dispatch 片、存活流数，不提供修改权。最大 dispatch 片只测一次调用/推进，不能代表连续 SIE-off 总区间。K3 无 S-mode 外部 IRQ 服务入口；常驻循环在无 Ready 但有装载/回收工作时连续推进，在纯等待时使用定时 WFI。K4 需在这些片间加入实际设备 IRQ 服务。K7 两编译任务背景的交互延迟尚未测量。
