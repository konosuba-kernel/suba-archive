# K4 工程过程记录

作者 root / k4_filesystem / k4_finish。K3 已独立验收并提交 `6162887`；K4 正式生产实施使用 C64 编译器 `22d2c81fd0dbfc6de6b3b13fb2f485b1c64913849d9e59eeabe8c2757d27ebf4`。生产 protected mount、U smoke、boot serial FLUSH 与两次启动证据在 `build/k4-protected-mount-r1`。E01–E08 保留当时探索证据及边界，不据此声称完整 K4 已通过。

## K4-E01：满节点目录校验的平方复杂度

- 类别：架构/性能难点；状态：探索修正并验证，待正式集成。
- 症状：逐对检测4096节点重名，原生QEMU用户态验证超过30秒；限制每次64步仅限制单次占用，无法降低总工作量。
- 证据：`build/through-k7-k4-draft/mount-r1/failure.json`、原实现副本；新版`check_mount.py`与`mount-r2/evidence.json`。
- 原因：普通满节点输入执行约八百万次节点对比较，初版还按值传递Node；不能据此声称单纯CPU或QEMU故障。
- 处理：挂载期8192槽名字哈希，冲突仍精确比较，逐次最多64个动作；复用块所有权scratch前8192项，使用后分片清零。21用例通过，包括满节点、末尾重名、目录环、链环、共享块、孤立块、16MiB文件；最慢约0.547秒。恶意哈希冲突仍有有限但更慢的路径，尚未专门测量。
- 改进参考：同时评估单片预算与整体复杂度；固定小索引有实测理由后再引入。按值复制的成本应在语言工具中更容易看到。

## K4-E02：轮询完成不能证明IRQ路径

- 类别：验证与架构难点；状态：探索已补强，正式集成待做。
- 首个probe只是设备完成后PLIC claim/complete，不能证明trap可达。
- 处理：`irq-r1/`只等待trap handler推进的完成计数，之后才消费used记录，真实读/写/FLUSH及关机重启读回通过。`irq-negative-r1/`清除SEIE，同一DMA传输必须超时panic106，未出现成功标记。
- 改进参考：明确什么观测真正区分中断驱动与轮询。正式版需结合K3用户态/idle/取消生命周期重新验证，裸S探针不能替代。

## K4-E03：opaque类型不能从模块外zero构造

- 类别：语言现行规则及诊断可用性；状态：已解决并在transport探索运行，正式集成待做。
- 症状：`transport-r1/probe.build`编译报`E_NAME file=4 byte=432`，位置是block模块尝试`static mut DEVICE: virtio::Device = zero`。
- 已确认原因：Device含私有字段；当前参考手册第2/4节明确禁止外部zero绕过封装；`compiler/types.vt::check_zero`检查字段可见性后报ERROR_NAME。这是有效规则触发，不是已确认compiler BUG。
- 处理：外部持有以无载荷Missing/Invalid起始的状态枚举，由初始化函数返回合法Device/Queue后发布；不把私有字段全部改public只为通过初始化。`transport-r1/`已重新编译并通过真实磁盘读/写/FLUSH及重启。
- 改进参考：E_NAME应能指出“opaque类型不可在模块外zero”及相关字段/类型，而非仅裸数字；研究显式未初始化容器/借用匹配能否减少外围枚举和大值拷贝，但不在本轮顺手扩语言。

## K4-E04：16位共享队列索引需要一次宽度正确的发布

- 类别：设备并发边界；状态：探索代码检查发现并修正，真实回绕回归通过。
- 风险：用两次byte store发布avail.idx，在低字节回绕时设备可能观察撕裂值；单hart不代表设备DMA与CPU串行。
- 处理：通用transport改用对齐16位store加fence发布；used.idx使用对齐32位read的高16位，序号按16位回绕。索引差不得超过64或已发布未消费数量，head需仍归设备所有。
- 改进参考：把MMIO/DMA宽度、屏障、所有权写在接口中；普通内存wire编码与设备共享控制字不可无差别复用。当前尚未证明实际出现过撕裂，不标记为已复现硬件BUG。

- 补充验证：`build/through-k7-k4-draft/transport-wrap-r1/evidence.json`，同通用transport连续65544次真实块设备IRQ传输，通过64个ring位置与16bit生产/消费序号回绕。这证明正常回绕路径，不等于已复现旧byte-store撕裂。

## K4-E05：分开证明纯校验与真实磁盘集成

- 类别：分层验证难点；状态：底层组合探索通过，生产服务待实现。
- 纯元数据harness的21例不证明驱动能读出正确数据。`build/through-k7-k4-draft/mount-disk-r1/`另用真实IRQ读取193个metadata块，调用相同codec/walker，再修改固定文件内容与节点长度、FLUSH、正常关机/重启并完整重新校验。
- 结果：两次实际boot及宿主只读最终盘字节一致。尚未实现完整namespace/syscall/取消/回收，不能借此提前接受K4。
- 改进参考：纯状态核心可反复复用，但每个外部边界仍须真实证据；测试报告应写明实际覆盖层次。


## K4-E06：永久 DMA 存储与非阻塞驱动边界（探索已验证）

固定 `0x81000000` scratch 只适用于早期裸 S 探针，会与正式内核增长后的 BSS/分配器冲突。新探针将 descriptor/avail/used/header/bounce 放入内核私有 BSS，预留六页并取页对齐的五页有效区；所有页随 kernel image 保留，不借用用户页、不跨等待借用栈。块层显式 Idle→Submitted→Completed，唯一上层取走完成后才再次提交；取消交付不撤销 DMA。

`build/through-k7-k4-draft/async-r1/results/evidence.json`：实际盘 read/write/FLUSH、正常重启读回通过。此探针通过 PLIC claim 服务确认完成，没有启用 trap，不替代此前 trap IRQ 探针，更不代表正式 U 态取消测试。机器存储地址、队列固定成本与借用前置条件需要在正式接口中明确；当前实现一块 4 KiB bounce，复杂度由串行 FS worker 承担。

## K4-E07：缺失 profile 绑定的诊断定位（规则与诊断改进候选）

新 `suba-kernel` 探针遗漏必需 `trap_dispatch` 绑定，编译返回 `E_NAME file=0 byte=0`。补全绑定后原源码可编译。这是正确拒绝缺失绑定，不是语言实现缺陷；后续可考虑直接指出缺失的 profile 绑定名字。原型清单位于 `async-r1/probe.build`，正式运行仍接 K3 的完整 trap bridge。

## K4-E08：中断使能与返回特权状态不可共用常量（静态审查修正）

正式接入 SEIE 时，原 trap return 连续使用同一寄存器设置 `sie` 和 `sstatus`，旧值32恰好同时表示 STIE 与 SPIE。把前者改成544（STIE|SEIE）不能让后者沿用，否则会额外写入sstatus的VS位。已在首次正式运行前静态审查发现并分开写入：sie=544，sstatus=32；未声称观察到硬件故障。后续 ISA/ABI 对照应检查寄存器值的实际消费位置，不能只搜索一个立即数。最终验证还需覆盖用户完整现场与非法特权访问。

## K4-E09：语言保留名字与聚合 zero 前提

- 类别：语言规则/诊断可用性；状态：生产实现编译期间遇到并调整，尚未完整验收。
- FS 的具体结果枚举取名 `Result`，在作为另一枚举载荷时触发 `I_UNSUPPORTED file=45 byte=694`。检查编译器 parser 可见 `Result` 被直接作为不支持语法保留，并非此次枚举设计本身被证明不可实现。已改为 `Outcome`。
- 队列记录包含首标签带载荷的 Command，`static ... = zero` 正确被拒绝（`E_TYPE file=45 byte=1093`）；将无载荷 SyncAll 放首标签，队列 Empty 状态仍是是否有效的权威，不借无效 command 执行业务。
- 改进参考：保留字诊断应区分禁用的泛型语法与具体类型名称；zero 前提可直接指出不可清零的字段及首标签，减少只凭数字偏移定位。以上不是已确认编译器错误。

## K4-E10：目录身份也必须跨取消转交

- 类别：架构/生命周期难点；状态：正在实际集成。
- K3 RAM fixture 的 `/boot` cwd 字符串不能冒充真实 FS cwd。K4 的 spawn 在 argv 校验后向同一串行 FS worker 排队 Directory 解析，得到真实目录 pin；Preparing/Installing 各阶段明确持有它，失败/取消释放，成功转交子进程。子进程结束时释放，unlink 拒绝删除仍有 cwd 引用的目录。
- 初始真实 cwd 为 `/work`；局部 RAM spawn fixture 使用绝对 `/boot/1`。K7 将映像字节 provider 换成 FS 时仍复用同一 ELF/loader，不新建第二套加载器。

## K4-E11：将物理页基线扩展为存储所有权基线

- 类别：验收强度/架构难点；状态：增加生产只读账本及实际故障窗口测试。
- 完全写满的盘只证明零块可分配时的失败；它不能区分“先预留部分块后失败”是否泄漏。测试另外先释放靠前的八块，再请求十六块，要求 NoSpace 后仍有八块、旧长度/epoch 不变，随后写八块必须成功；Reserve 期取消同样检查实际预留不为零。
- 生产维护可分配 FAT/节点计数，更新点是 mount、reserve/rollback、create/free；文件对象/请求计数按至多64项扫描，另报告 DMA state 与 detached 节点计数。退出验收同时比对这些账本，不能以物理页相同替代磁盘空间无泄漏。

## K4-E12：把指定 DMA 的 U 态 IRQ 与调度轮询区分开

- 类别：测试设计；状态：实跑中，不提前声明通过。
- 累计 `user_traps > 0` 可能来自另一项I/O。测试快照在第二块数据 DMA 前屏蔽 PLIC，保留真实 Submitted 状态；父进程从用户态调用 kill_child。kill 仅登记释放，下一次选中用户、即将 sret 时才恢复 PLIC；该块完成在 hub 消费前必须看见新的 U external trap。
- SEIE 关闭的同一快照必须因上述断言停机；没有伪造 used 状态、回调或 DMA 数据。生产 transport 与 block 均保持原逻辑，控制仅在忽略的测试构建快照。

## K4-E13：测试自身误用已消费的 Child 句柄

- 类别：测试错误；状态：已定位并修正 fixture；`build/k4-cwd-r3` 两次启动通过。
- `build/k4-cwd-r1` root exit108。测试在 collect成功后再次close Child；K3既有collect合同已关闭该句柄，因此返回BadHandle符合合同，不能计为cwd泄漏或内核BUG。fixture改为直接检查删除原cwd目录与下一次失败spawn的资源状态。

## K4-E14：异步 unlink 的完成与空间回收不是同一时点

- 类别：测试基线错误；状态：`build/k4-cancel-reserve-r2` 每次启动100轮、两次启动通过。
- `build/k4-cancel-reserve-r1` 在第一次取消后退出88。准备阶段刚 unlink 八块的 `aaa_hole`，立刻记录 FAT/node 基线，把仍在独立清理的节点也计入。取消完成后的清理结果不能与这个中途状态直接比较。
- 修订：观察 detached 数量回零后才记录取消实验基线；同时把合并的退出88拆成具体 ledger 项退出码，避免错误诊断。修订后真实部分预留取消每轮恢复全部账本，生产源码无须为此修改。
- 同类合同通过独立 `build/k4-unlink-reader-r1` 证明：unlink 后名字和 LIST 立即消失、旧 reader 仍读到原字节，close 后 FAT/node 各释放一项，再启动只存在保留的中文名字。

## K4-E15：部分预留失败需要保留后续可用性证据

- 类别：测试补强；状态：`build/k4-disk-partial-r2` 两次启动通过。
- 真实盘只剩八个可分配数据块，请求十六块写入时确实经过部分 reserve；要求 NoSpace、旧长度和 source epoch 不变、仍有八块可用。随后同一文件写八块成功并 sync；删除清理后再次有八块，连续四轮。
- 这是比“全满盘立即失败”更强的回滚证据，不能用前者替代。全满盘仍保留 `build/k4-disk-full-r1`，满节点保留 `build/k4-node-full-r1`；加入 ledger 后最终生产输入分别在 `build/k4-disk-full-r3` 和 `build/k4-node-full-r3` 复验通过。

## K4-E16：恢复 PLIC 后的第一个 trap 可能仍是 ecall

- 类别：测试时序假设；状态：放宽不成立的首trap断言后仍失败，后续定位见E20。
- `build/k4-cancel-dma-r3` 第一次真实 kill 后 panic71。测试要求恢复 PLIC 后首次 schedule claim 必须已经有新的 U external trap，但父进程的下一次快速 ecall 可以先于异步 IRQ 信号传播；这不是生产内核必须满足的时序保证，但不能仅凭该可能性解释实际故障。修订后 r4 仍因deadline停机，实际设备模型原因在E20。旧报告保留失败，不能拿同样失败的 SEIE-off 负控证明正控有效。
- 修订仅在测试快照：指定 completion 待验时，若尚未观察新的 U external trap，暂不从 PLIC claim；父进程继续在 U 态检查 guard 并保持 runnable，直至该真实写事务阶段结束。新的 U external trap 后才允许原驱动消费 completion。未修改 used ring、DMA 内容或生产 block/transport。
- 这证明受控取消窗口里的 U IRQ 路径可达，不证明生产所有 completion 必须经过 U trap；生产还允许在普通调度/idle 的 PLIC 服务点处理 IRQ。SEIE-off 负控应由原 block deadline 停机 panic73。

## 正式生产输入追踪

`build/k4-filesystem-r3` 的生产输入是当前 K4 候选起点，内核 ELF 为 `c1161fe1423733281cdcb3f1f5e773fe80c35fe6bfc46450107e3f2c39085480`。E01–E08 的改动已集成，但其早期探索目录仍仅证明当时那一层行为。

最终生产输入已复验 `filesystem-r3`、`boundaries-r3`、`disk-full-r3`、`node-full-r3`、`cwd-r3`、`disk-partial-r2`、`unlink-reader-r1`；它们每个均有两次正常启动，同一实际 raw 盘经 FLUSH 后重读。旧 boundaries/full/node 的 r1 在加入 storage ledger 前运行，保留作为历史证据，不冒充最终输入验收。

真实坏盘与设备 I/O 错误由 root 的 `build/k4-faults-r2` 完成12例，见 [故障证据](K4-fault-evidence.md)。这覆盖纯元数据测试不能证明的实际挂载失败、运行期数据/元数据失败、FLUSH失败以及完成未交付时原 block deadline 停机。

取消控制与 fixture 的新 revision 仍须以最终报告为准。本文件是过程记录，独立候选报告给出整个阶段是否接受。

## K4-E17：Transient 权限不能只检查 open

- 类别：真实实现 BUG；独立 review 提出，旧版实际反例失败，新版已两次启动验证通过。
- `open_existing` 已拒绝他人打开尚未 seal 的 Transient；但 namespace unlink 和 replace 的目标侧仅检查 writer/cwd。创建者 write 后 close 而保持存活时，另一进程可以删除或替换该未发布节点。close 不是发布，所以这违反所有者生命周期。
- `build/k4-transient-owner-old-r1` 在旧生产 ELF 上 root exit175：父进程先创建、写入并关闭两个未 seal 文件，再 spawn 子进程；子进程的 unlink/replace 必须均为 Denied，旧实现不能满足。两个操作都执行后才比较，避免第一个失败遮住第二个；父存活时间由等待子退出保证。
- 新证据：`build/k4-transient-owner-r1`，子进程 open/unlink/replace 均拒绝，父进程逐字节读回原内容；退出后清理、下一次启动重新创建同名节点成功。
- 修复：同一 `accessible(node, client)` 谓词供 open 和 namespace 已解析节点使用；replace 另外检查已存在目标节点。普通共享文件不引入新的访问控制；当前 Transient owner 仍可主动删除自己的节点。
- 改进参考：对象权限应覆盖所有以名字解析到该对象的操作；独占 writer 是并发租约，不能代替创建者权限。

## K4-E18：cwd 继承的是目录 pin，不是启动字符串

- 类别：真实实现 BUG；独立 review 提出，旧版实际反例失败，新版已两次启动验证通过。
- 空 cwd 的 spawn 复制父 argv 中的 cwd 拼写，然后重新解析。父以 `/work/temporary/..` 启动时实际目录 pin 为 `/work`；删除空的 `temporary` 后，启动字符串不再可解析，但真实 cwd 仍完全有效。旧代码错误返回 NotFound。
- `build/k4-cwd-identity-old-r1` 在旧生产 ELF 上 root exit205：第二层进程删除 temporary，然后以空 cwd spawn 第三层，第三层应在 `/work` 创建相对路径文件；旧实现不能完成。
- 新证据：`build/k4-cwd-identity-r1`，三级进程链两次启动通过，第三层继承真实 cwd 后相对创建成功；`build/k4-cwd-r4` 与 `build/k4-unlink-reader-r2` 同时复验旧pin/reader回收合同。
- 修复：FS `retain_directory(parent)` 直接取得当前已解析目录身份的一份拥有 pin；Preparing 的 Inspect/Create/Installing 沿用现有释放/转交路径。argv 保留原显示字符串，不作为 cwd 权威。显式新 cwd 仍经过 Directory 请求解析。
- 改进参考：把显示形式与持久身份分开；继承操作应复用已经持有的能力，不能无意重新授权或重新解析可变化的名字。

## K4-E19：局部所有权修复的栈与产物成本仍需可见

- 类别：语言工具/可维护性观察；状态：已记录实际编译差异，不据此推断栈溢出。
- 两项所有权修复前后，50个VT源文件保持不变；编译器报告 max_frame 从9344增至10368，text 从1205248增至1210836字节，ELF 从1216544增至1220640字节。证据为 `k4-filesystem-r3` 与 `k4-filesystem-r5` 的 verification 编译输出。
- 增加具体 enum/pin转交不会自动是零成本。当前报告只有全局最大值，未直接给出函数名或调用链；后续工具改进可输出“哪一函数、哪些按值聚合临时量、调用链预算”。单函数 max_frame 既不等于全链路峰值，也不直接证明溢出。真实 spawn/继承/退出测试继续使用已有带guard的S栈。

## K4-E20：测试恢复 PLIC enable 后设备模型未重新计算 IRQ 线

- 类别：设备模型/测试控制难点；状态：root完成寄存器诊断，修订正负控已验证；非生产 trap 实现 BUG。
- `cancel-dma-r4` 把普通调度 claim 延迟到真实 U external trap 后，仍在第一次取消后panic73。QEMU `-d int` 有一个外部trap，但它发生在测试mask之前，不能证明目标completion可达。
- root诊断观察到设备和PLIC已pending而CPU sip仍为0，详见[IRQ诊断与模型证据](K4-irq-diagnosis.md)。测试仅恢复enable，未使本地QEMU11.1.1重新评估对CPU的外部中断线。
- 对照[QEMU官方master的sifive_plic.c](https://raw.githubusercontent.com/qemu/qemu/master/hw/intc/sifive_plic.c)（2026-10-16读取）：enable写分支更新数组而不调用update，threshold写分支调用update。源码与实测机制相符，但未把master等同于本地二进制的完整源码版本。
- 测试快照修订：恢复enable后再写threshold0，触发模型重评估；继续要求真实U external trap，然后让原驱动消费DMA完成。生产 `hub::enable` 原本就写threshold0，未作任何改动。最终正控 `build/k4-cancel-dma-r5` 两次启动各100次取消通过，U external trap分别392/398次；每轮存储账本和物理页恢复。负控 `build/k4-cancel-no-irq-r3` 首次取消后由原block deadline停机panic73，无成功标记。
- 改进参考：调试受控时序要同时检查设备status、PLIC pending/enable/threshold和CPU pending；不能把“有pending位”或“另一时刻有U IRQ”当目标链路的证明。

## K4-E21：失败创建仍可能使 source_epoch 前进

- 类别：非阻断架构改进候选；状态：独立review静态发现，按本轮决定暂不扩大修复。
- `create_operation` 先调用 changed()，随后若 File 表已满，open_existing失败并通过free_node撤回新节点，但source_epoch已经增加。没有遗留新文件或数据一致性损坏；当前合同没有承诺所有失败操作都不递增epoch。
- 对K7的潜在影响是快照重试可能保守返回Busy，而非发布错误快照；还会消耗一次epoch。后续可把epoch推进集中到可见提交点，或明确其语义为“可能修改过源码的保守版本”。须同时考虑预留、取消和其他失败路径，不能仅回减一次计数而破坏单调性。此项不作为K4阻断，也不声称已作实际容量复现。

## K4 实施收尾输入

最终普通生产快照为 `build/k4-filesystem-r5`，SHA256 `87451fecfd59ed3df7f64f2a6e15e19448b1990ec7ed2274eb724ca14e405127`。权限/目录身份修复后，filesystem、两个BUG正控、cwd、unlink-reader、boundaries、全盘/部分预留/节点满均在最终输入上通过两次启动；DMA取消也使用最终输入。作者证据索引为 [K4-filesystem-evidence.json](K4-filesystem-evidence.json)。

Input-copy和Reserve取消各100轮×两次启动的证据保留 `cancel-pre-r3`、`cancel-reserve-r3`，它们在最后四文件修复前运行；fixture使用owner自己的Transient和显式`/work` cwd，不受新增他人权限判断/空cwd继承分支影响。索引明确列出源文件差异，不把旧ELF标成最终候选；独立验收者核对这一影响判断。最终判定和提交仍归独立验收流程。
