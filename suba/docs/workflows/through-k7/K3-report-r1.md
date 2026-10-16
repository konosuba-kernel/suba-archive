# K3-r1 实施报告（待独立验收）

作者 `/root/memory_resume`；探索草稿贡献 `/root`；独立验收者 `/root/ram_acceptance`。基线 suba `72e19fb766dee001cfd2ff0ea824786366e9ec24`，K6 `3cceb87` 已接受。本代理在环境中断后依据真实文件继续实施，未重写旧 K2 冻结记录。沿用原 E3 `049c6e094ccd044fba3b5d357583013b77f0e8e9a98d431ad919e02b0cda2144`，未切换随后接受的 C64，也未修改编译器。不自行提交。

## 实际交付

- 真实 U ecall 与 `user/libsuba`：明确状态/值、参数字节记录、全量范围与权限校验，SUM=0。raw S0 跨 ecall 使用 x28 保存返回值指针，完整寄存器恢复沿用 K2。未知调用与尚未实现族返回 Unsupported。
- objects 独占每进程64个 generation handle 与 rights；stream 独占32个64KiB环及端点引用。一次用户范围≤64KiB，实际partial≤2KiB，两次搬运合计≤4KiB；EOF、BrokenStream、NONBLOCK和阻塞均由实际对象状态决定。
- request 独占每进程一个代数token，owns 与可交付active分开；wait最多16个watch，所有条目先验证，level条件与deadline在同一串行调度器裁决。Dying先撤销交付，迟到完成无法copyout。
- spawn使用同一生产ELF decoder/loader，准备、两次2KiB argv快照、参数验证、ELF/退出记录保留、创建、句柄安装、逐页装载、RO参数页发布分别推进。cwd继承来自父只读参数页；只继承显式stdout/stderr writer。普通spawn没有特权参数。
- 子进程退出记录在创建前预留。未绑定reservation属于Request；已绑定但未安装句柄的Child引用仍属于Request；安装后归父句柄表。对应取消分别abort/release，子进程本体统一子树回收，避免隐形引用泄漏。两个转移窗口均有定点取消实测。
- children/job保留父子生命周期边；关闭Child放弃收集权，不解除父退出取消树。JobEnd、父退出逐层终止后代，父Tail等所有孩子完整收尾，整个过程无内核递归。JobDone不早于孙进程回收。Job输入冻结诚实返回Unsupported，FS冻结/事务留待K4/K7。
- ranges持有动态VA范围，space独占Frame与页表。精确free、可复用账本槽、物理页→slot索引与空页表计数支持长期alloc/free；失败逐页回滚并剪空表。96MiB配额含页表与外部所有者计账，window未来可charge/uncharge而不重复拥有Frame。
- process增加Prepared/publish、per-Id分片reap与独立publish_exit。回收顺序为撤销请求、取消子树、逐个关闭句柄、用户页、尾门。K4可在尾门等待已提交设备/FS引用，不能提前复用身份。正式入口常驻，Blocked不等于系统结束；测试终点仅注入到副本。

RAM `/boot/0..7` 仍仅是K3字节provider；没有第二套ELF loader，也不读宿主文件路径。现有启动描述符、保留范围、同一原始kernel ELF身份要求继承K2。K4替换真实FS提供者。使用者记录见 `K3-reference-r1.md`；边界和已知限制亦在其中。

## 验证

复现命令与精确断言见 `tests/k3/README.md`，原始输入/命令/日志在ignored build；compact身份索引见 `K3-evidence-r1.json`。不同迭代的源快照有各自哈希，未将较早测试冒充最终二进制完全相同。

| 检查 | 实际结果/证据目录 |
|---|---|
| ecall、页零化、流基本生命周期 | k3-smoke-1通过 |
| 128轮反复alloc/free、部分/重复free拒绝、513页跨叶表 | k3-memory-1通过，逐次完整页基线 |
| 真实96MiB配额失败回滚 | k3-rollback-1通过，不缩小生产配额 |
| 分配0/1/2次后失败 | k3-allocation-0/1/2均通过，连空页表一起回收 |
| 满环/背压、错端、RO与坏跨页、有效跨页、partial | k3-streams-final及2KiB版本k3-streams-sliced通过 |
| argv/cwd、显式继承、128KiB完整流、collect/stale | k3-spawn-final通过 |
| 父子孙JobEnd、直接父退出 | k3-tree-final、k3-orphan-tree-1通过 |
| 16watch、deadline、kill/重复kill、stale Child | k3-waits-final通过；kill时owns保留而active/copyout拒绝 |
| 64句柄及第二端插入失败 | k3-handles-1通过；无端点泄漏 |
| 16进程容量、预留记录后Full、后继槽复用 | k3-process-limit通过 |
| 阻塞writer被kill、缓存不受迟到写影响、EOF | k3-blocked-writer-1通过并观察迟到交付拒绝 |
| 畸形argv、路径、错误及部分继承失败 | k3-spawn-invalid-2通过 |
| 未绑定reservation取消、未安装Child引用取消 | k3-cancel-reservation、k3-cancel-install-final通过，全引用/页基线 |
| 去除空表剪枝负控 | k3-negative-prune-1准确用户退出15 |
| 去除token交付资格负控 | k3-negative-token-1准确panic23 |
| 只检查首页面负控 | k3-negative-usercopy-1准确panic22 |
| K2完整寄存器、32次创建回滚/真实配额、硬件guard | k3-k2-registers-1、k3-k2-rollback-1、k3-k2-guard-final通过 |
| ELF边界 | k3-elf-final全部37例通过 |

失败证据保留：k3-compile-1/2/3分别为重复import、导入/函数名冲突、私有Id不能zero；不是已确认错误代码生成。k3-spawn-invalid-1为测试误写cwd_offset并错误恢复，修正真实reserved偏移52后通过。工程记录逐项区分语言限制、内核缺陷、测试缺陷与未证实推测。

## 时延结果与限制

5ms是测量目标，不把功能通过等同于目标达成。早期tree最大15.0792ms、waits13.5132ms；依次分离spawn工作后，无其他节点QEMU的同一产物三次冷启动8.635/8.672/8.708ms，后续5.264/5.233/5.060ms。两组完整记录均保留，不能只挑最好值。

最终tree一次测得4.7593ms，最终cancel-install一次4.7225ms；其他最近用例仍有5.1355/5.4773ms，均是kind32（ABI SYS_STREAM_CREATE）的固定元数据路径。kind2才是spawn；一次进度消息曾解释错kind32，已更正，原始数值没有修改。不再为了临界冷启动数值无限增加状态，也未把原因未经证实归给编译器或TCG。

`max_slice`只覆盖一次dispatch.call/step。无Ready而仍有工作时，schedule可连续执行多片，**不代表整个SIE-off或连续S驻留上界**。K3没有S-mode外部IRQ服务入口；K4要在实际片间服务IRQ，并测pending IRQ到处理的最坏延迟与连续S驻留，不能插空WFI美化指标。K7两个编译任务背景下99%≤100ms交互延迟尚未测量。工具将timing单列，可用`--require-slice-target`把5ms作为额外失败条件。

## 实际成本

正式生产ELF：`build/k3-production-r2/build/kernel.elf`，SHA256 `d186379f2df7717d0a42628df03fcd001f8168a211f07dc5c9f07a290e70a80c`。30个VT源共4772行/217442 B，2个S0共261行/5181 B；清单含ABI和既有platform代码。text687844 B，ELF696336 B；PT_LOAD内存跨度12028416 B，BSS11336176 B。最大单函数栈帧9344 B，不宣称已形式化证明最深调用链栈界。

实际编译器sizeof（测试副本访问私有类型，未公开生产字段）：

| 存储 | 单项 / 固定成本 |
|---|---|
| Frame / Owned | 8 B / 16 B；Hole携带usize令Owned较K2的12 B增加对齐成本 |
| 用户页账本 | 16×24576×16 = 6291456 B（6 MiB） |
| 物理页slot/children索引 | 131072×8 = 1048576 B（1 MiB） |
| 既有allocator元数据 | 131072×12 = 1572864 B（1.5 MiB），未优化容量 |
| 内核页账本 / space记录 | 16384 B / 16×56=896 B |
| process记录 | 16×736=11776 B |
| 句柄Slot | 1024×48=49152 B，另owner身份128 B |
| stream缓冲 / State | 2097152 B / 32×48=1536 B |
| Child / Job | 64×104=6656 B / 32×24=768 B |
| Request / VA Table | 16×312=4992 B / 16×1552=24832 B |
| argv快照 / ELF Plan缓存 | 65536 B / 5376 B；不内嵌进按值Request |

这些固定成本均属于上述BSS，不能再加一次。运行期另付实际页表、共享内核栈、每个用户1MiB栈与映像/参数页。动态free用孔位复用，配额随live count而非高水位增加；reap每次最多访问16槽，含Hole。设备页quota支持保留给K5；未声称已有DMA排空实现。

## 可维护性说明

所有者为space/process/objects/stream/request/children/jobs/ranges；顶层dispatch协调它们，叶owner不回调dispatch。dispatch按调用、流、页、spawn分文件，但仍是一个串行协调所有者；S-next imports是module级且拒绝重复，因此仅dispatch.vt列imports，其余文件明确说明。没有为节省源码清单容量拼接源文本。

保留具体枚举、早返回与局部纯字节校验；固定容量及大buffer归属均能从声明定位。语言的单载荷枚举、无枚举相等和私有类型构造限制形成部分嵌套match，未引入通用异步框架。后续FS/window增加新的真实操作时继续扩展已有生命周期门，而不是复制一套关闭/回收实现。
