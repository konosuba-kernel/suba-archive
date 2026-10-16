# K7 内核实施记录

基线：K5 `92c76d2`（K4 `10de32f`、K6 `3cceb87`）；编译器固定为
biomiya `bd73055` 的 C64 E3，SHA256
`22d2c81fd0dbfc6de6b3b13fb2f485b1c64913849d9e59eeabe8c2757d27ebf4`。
本文记录实施中的边界与证据，不把尚未通过的实现写成验收。

## 内核接口与所有者

- `abi/image.vt` / `suba::image` 是原 ELF 纯检查器的迁移；Plan/Segment/Inspect
  与inspect(header,total,kernel)不变。READ/WRITE/EXECUTE=2/4/8与space核对相同，
  不引入内核状态到U，kernel以alias elf消费；用户发布检查复用同一实现。
- `image_reads` 拥有每个FS client的一份来源代数、reader引用、ticket和4KiB buffer。
  Open→Stat→Header与逐页Read共享FS串行owner；header/数据只在当前片借给原loader。
  取消先撤ticket交付，再关reader；FS请求pin保留DMA尾部，process Tail仍等settled。
- 普通spawn从真实FS解释路径；仅启动固定RAM来源保留。父cwd用于解析映像，
  映像inspect完成后再借/解析child cwd，不在同一client并发排两个FS请求。
- Job准备域仅授creator。选定compiler及其后代继承受限域；job=0不能重新获得
  普通/work权限，新建Job不能放大权，Prepare不通过普通spawn继承。存储hold
  晚于进程/请求/DMA/目录树清理释放，避免Job代数提前复用。

## K7-K01：带载荷首标签的枚举不能用zero假造初始值

- 类别：新实现语法误用；证据：`build/k7-image-compile-r1` 报
  `E_TYPE file=30 byte=5646`，定位image_reads的`var result: fs::Outcome = zero`。
- fs::Outcome首标签Value带usize载荷，改为明确`fs::Outcome::Value(0)`；没有修改
  编译器、扩大语言承诺或把诊断记成生产运行BUG。后续编译/运行仍须独立通过。
- 启示：协议结果初始化应可读地说明暂存标签，不能把zero当作所有sum type通用构造。

## K7-K02：发布边界沿用根工程记录E04

- 类别：跨调用生命周期缺口；此前K4源只允许flags=0进入replace。
- 实施将本owner已关闭writer的Transient源在同一名字commit撤销Transient；
  外部owner仍由accessible拒绝。用户序列为sync(false)/close→replace→sync_all。
- 提交前退出应回收临时节点，提交后退出保留发布物；旧读者继续引用旧destination。
  这些是必须运行验证的反例，当前代码改动不替代证据。

## 首轮运行证据（生产内核，无测试hook）

`build/k7-job-compile-r1` 是63VT生产源码编译快照，ELF1663032字节；
`verification.json` 明确只声明宿主编译成功，不能把它视为运行验收。
以下三个探针复用该ELF，并逐文件核对manifest输入与编译器哈希：

- `build/k7-kernel-images-r1/verification.json`：真实FS映像10次spawn/collect，
  父cwd的相对来源解析，坏映像/RWX/缺失/坏child cwd拒绝，reader和页回基线。
- `build/k7-kernel-job-r1/verification.json`：真实Job目录、boot/epoch不符拒绝、
  Frozen写/命名修改拒绝、旧writer的Write/Stat/Sync撤权、compiler及job=0孙代
  不能取得/work写权或新建Job；JobEnd后块/节点回基线，旧引用安全close。
- `build/k7-kernel-publication-r1/verification.json`：尚未关闭writer时Busy，
  自己的closed Transient替换成功，旧destination读者仍读旧内容，最终sync_all。
- `build/k7-kernel-death-r1/verification.json`：真实U stdout握手确认commit前后边界；
  另一进程不能读取/替换尚未发布的Transient；kill提交前owner后临时节点消失，
  kill提交后owner仍能读到发布物；两个分支检查节点/块归还。

这些探针由指定可信U controller仅通过普通显示grant报告；它的被测子进程全部走
真实FS spawn。测试由宿主在绿色结果后停止QEMU，因此这里没有声称正常关机或
掉电恢复已被覆盖。正式集成另须重复完整工作流。

## K7-K03：取消观察点必须绑定具体状态机函数

- 类别：测试观察器BUG，不是生产BUG。`build/k7-kernel-load-cancel-r1`实际失败98，
  没有达到预期提交窗口；逐函数核对发现Read提交文本锚点匹配的是
  prepare_write内部的EdgeReading，普通Read使用submit_read且有额外范围条件。
  因此早先以为它覆盖header的推断也不成立，不能列作任何装载取消通过证据。
- 修正为函数级submit_read锚点，并限定OFFSET非零：header固定offset0，ELF
  LOAD页读取在process::begin之后。Job输出限定第二数据块Write提交，独立于此错。
- 未完成的`build/k7-kernel-no-user-irq-r1`在明确识别同一观察器错误后停止宿主
  编译，记录code=-15、未进入guest；不把它计作有效IRQ阴性对照。r2重新冻结。
- 观察器只延迟真实PLIC IRQ，不伪造used ring。真实U父进程调用kill或JobEnd，
  下一次U返回恢复PLIC并要求实际U external trap。正式阴性对照也须到同一窗口。
- 启示：唯一文本匹配并不保证语义正确；必须读到所在函数和前后状态迁移。
  失败报告、冻结输入与测试版本必须保留，不能用预计覆盖范围代替实际达到的状态。

`build/k7-kernel-job-r2/verification.json`补充无hook权限反例：外国普通进程
不能访问Preparing或Frozen src；job=0不能借Job cwd；creator Frozen out写拒绝；
纯K3进程Job freezeUnsupported及坏JobInfo输出指针Invalid。旧writer安全close与
资源基线继续通过。

## K7-K04：Frozen只读句柄仍可seal的元数据写权缺口

- 类别：生产权限BUG，已用旧组合真实复现；
  `build/k7-kernel-freeze-seal-negative-r1/verification.json`失败120。
- 位置：`kernel/fs/operations.vt`的`begin_operation → Command::Sync`。
  原逻辑仅检查Transient owner；Freeze只撤销Source的Write lease，creator可以
  在冻结前close writer后open Read，再于冻结后通过这个只读引用seal该节点。
  seal虽不改数据字节，却改变生命周期/对其他进程的可见性。creator预留out旧
  writer也能借同一入口绕过冻结后compiler独占out写权。
- 修正：seal在FS实际执行点检查`permitted(NODE,true)`，在任何磁盘写入/dirty
  之前Denied；普通sync(false)只是刷盘，继续允许仍有效的读引用。没有把readonly
  File token误当成树的写授权，也未扩大Job对象或新建第二套权限逻辑。
- 新探针同时覆盖src旧Read与out旧Write；negative-r2在修复前冻结，job-r3在
  修复后冻结，预期用相同U映像完成坏→好对照；以实际报告为准，编译中不算通过。
- 启示：内容写与命名操作之外，seal等生命周期状态也有写语义。权限审计必须按
  实际副作用分类，不能仅靠syscall名字里有没有write或File对象的初始rights。

## 取消证据与尚待解释的失败

- `build/k7-kernel-load-cancel-r2/verification.json`完成100轮真正Loading中的FS
  reader DMA取消，85.69秒，页/文件/请求/块状态回基线。
- `build/k7-kernel-no-user-irq-r2/verification.json`是故意关闭U external IRQ
  的阴性运行：实际达到第一个提交取消窗口，随后设备1秒watchdog使内核panic73。
  不把这一expected rejection记录成系统成功运行；将核对同U ELF并单独写比较报告。
- `build/k7-kernel-job-dma-r1`第61个提交窗口后失败100；原断言混合了提交状态
  未消退与collect不符，必须保留并复现，不能只凭次数推断内核BUG。
- `build/k7-kernel-job-dma-diagnostic-r1`把每轮增加一个job=0等待孙代及跨代旧
  Revoked引用，第81轮期间触及原180秒总限；此前断言未失败，但不是100轮通过。
  没有放宽guest限时。正式100轮保留单独的一轮派生子树覆盖，另外保留原场景
  只增加失败诊断的重跑，以查明原始失败是否再现。

## 修复后候选与最终专项证据

生产63VT内核为`build/k7-kernel-job-r3/build/kernel.elf`，SHA256
`0dc8ef589248f4b6845607346b933ff7f592fba67b1b74680554d72db2ef981d`。
下表每项均保存`verification.json`、`run.json`、串口/QMP/最终像素与源码哈希；
无hook项复用这一个生产ELF。用户fixture及host脚本不是生产系统实现。

| 报告目录（均在build/） | 结果与覆盖 |
| --- | --- |
| k7-kernel-job-r3 | 通过，7.98s；Freeze/外owner/派生权限/撤权与回收；`freeze-seal-comparison.json`确认坏→好两边U ELF相同，内核源码唯一变化operations.vt |
| k7-kernel-images-r2 | 通过，10.40s；真实FS路径/坏ELF/RWX/child cwd失败/10次spawn及reader基线 |
| k7-kernel-publication-r2 | 通过，3.03s；closed Transient同一步发布、open writer拒绝、旧reader保持、sync_all |
| k7-kernel-death-r2 | 通过，5.03s；真实U握手定位发布前后owner死亡、foreign Transient拒绝、资源基线 |
| k7-kernel-job-owner-r1 | 通过，27.01s；10轮kill实际Job creator，保留Job/Child句柄直到死亡，隐式结束选定compiler子树，真实目录/块/File/请求/页回基线 |
| k7-kernel-load-cancel-r3 | 通过，79.37s；最终修后内核加snapshot观察器，100轮真正Loading中真实FS read DMA取消，每轮资源基线 |
| k7-kernel-no-user-irq-r3 | 预期拒绝，4.29s；同U ELF、内核仅trap.s0关闭U external IRQ，第一个已观察提交窗口后真实设备watchdog panic73；`load-cancel-r3/irq-comparison.json`保存差异 |

取消观察器修改的是snapshot源文件，只有PLIC时序门与只读计数/观测入口；生产
源码不含这些入口。没有改ELF机器码或伪造驱动完成。装载与Job输出使用同一
观察kernel；最终Job输出100轮报告另在`k7-kernel-job-dma-r3`。

原Job取消首轮失败仍保留：同一旧r1 kernel/boot/user ELF完全不变、fresh disk的
`k7-kernel-job-dma-exact-replay-r1`与r2分别完成100轮（131.28/139.16s）；
原场景只增collect诊断的`k7-kernel-job-dma-original-diagnostic-r1`也完成100轮。
扩展旧Revoked句柄跨100代、一次job=0等待孙代的`k7-kernel-job-dma-r2`完成100轮
（140.97s）。这些不能解释第一次混合断言失败，更不能把失败改成通过；它仍是
一次未复现且缺少细分状态的记录。后续fixture已分开117（提交状态）/118（collect）
并保存wait/status/cause，供独立验收或再次出现时定位。

性能与后续清理：FS-backed Preparing/Loading的has_work仍沿用早期RAM加载阶段
的可推进判断，在等待DMA时可能额外跑有限32片。这是待测的调度效率问题，
当前没有以增大片预算或延长期限掩盖。`copy_arguments`的旧注释“no resource
is held yet”现只适用于尚未保留Child/cwd，不适用于已存在的image_reads来源；
正确所有权以本记录及该owner实现为准，后续教学整理应更正该旧注释。

最终`k7-kernel-job-dma-r3/verification.json`已完成100轮，133.52s，包含一次job=0等待孙代与旧Revoked句柄跨100次Job/inode复用。
`build/k7-kernel-final-evidence.json`逐项核对七个正例的原始生产输入均等于当前源码，
同时区分无hook生产ELF与snapshot观察ELF，并列出owned代码哈希。作者未自行提交或宣布独立验收。

## K7-K05：SyncAll持久化旧reader节点后，下一启动误判坏盘

- 类别：生产持久状态与挂载协议不一致，真实GTK全链路复现，K7-r1验收不通过。
  `build/k7-desktop-r1/first/disk.raw`与`reboot/disk.raw`原件均保留；SHA256为
  `17a23ce4a3ae8996a9f90c9abd6a31b9d151f782af9c8dc7e52f14e680df82a9`。
  first末次保存已完成SyncAll，新源码/笔记/ELF字节正确，随后同盘启动panic70。
  不归因为宿主停止方式，也不把第一段GUI操作通过当成整个闭环通过。
- 只读定位：`build/k7-remount-diagnosis-r1/checker.json`使用原生产纯校验器得到
  Fault{kind:4,index:10}；node10为Detached旧`/work/hello.vt`，generation4、73B、
  first=last=1148。磁盘没有reader计数，不能判定它当时仍被reader持有还是尚未被reaper扫到。
  SyncAll允许持久化这两类完整旧版本，而mount_check阶段2
  无条件拒绝非零flags。`nodes.json`、原始metadata.bin及新校验器结果均保留。
- 修正：合法Transient/Detached仍必须通过完整父链、块链、长度、独占分配验证；
  只有Detached不参加可见名字唯一性检查，Transient名字仍然参加。全部验证成功后，
  新boot无旧reader/owner，按64项预算标记并复用既有reaper回收，再复用串行SyncAll
  写回、FLUSH，最后写新boot serial并FLUSH，才进入Ready。不是容忍坏链后做修复。
- 同时修复一条派生不变量：目录删除原先忽略Detached子节点，可能在旧reader仍存活
  时释放父目录。现在返回Busy，直到最后reader关闭、旧节点回收后才可删除。没有
  等待所有系统reader关闭来完成普通保存，避免无关reader无限阻塞保存。
- 对分片回收/Sync交错的分析：CLEAN_NODE有效时cleanup_step每片必返回true，worker
  不选新请求；整个链清完后才允许Sync开始。ACTIVE事务期间不执行reaper，settled
  和Job drain也要求ACTIVE空闲。因此“释放一片FAT但旧bytes/last被Sync写出”在当前
  串行状态机不可达；仍添加65块回收后立即Sync及65块跨启动清理用例验证边界。
- 语言/架构启示：运行时不可见不等于持久化时不存在。写盘与读盘必须共享生命周期
  状态模型；纯元数据校验需要覆盖实际writer能生成的全部合法状态，而不仅mkfs初态。
  “文件字节保存成功”与“整个盘可重新挂载”必须有不同验收断言。
- 专项结果：`build/k7-remount-metadata-r1/verification.json`141项纯codec/validator
  用例通过，包括三种合法flags、Detached同名、Transient同名拒绝、无效父链、生命周期
  节点坏链/共享块拒绝及65块链。真实原盘复制重启与多次启动证据待后续补入，纯验证
  通过不等于设备持久性通过。

K7-K05修复后的生产内核：`build/k7-kernel-remount-build-r1/build/kernel.elf`，
SHA256 `2f073509c6af8bce081ec60927e82db836b40fc678582ed0b831903efef88bd3`，
仍为63VT，普通publication用例2.49s通过。生产源码与专项tests/tools已停写。

| 专项报告（build下verification.json） | 实际结果 |
| --- | --- |
| k7-kernel-recovered-r1 | 原GTK失败盘复制启动2.89s，随后复制输出盘再启动两次3.31/3.35s；163个live节点、2972个分配块，全部published文件SHA保持；原件未改 |
| k7-kernel-remount-r2 | first4.26s，后两boot2.81/2.63s；确定持有旧reader的flags2、Transient65块flags1、Transient+Detached旧reader flags3并存，启动全部回收；U内存free节点/块与disk账本均符合初始基线（另加一个持久ledger文件），两次重启后10节点/144块 |
| k7-kernel-remount-malformed-r1 | 对上一正例盘的复制件分别制造临时链断裂、共享块、孤立分配，纯checker分别返回fault8/9/11；真实生产内核全部panic70预期拒绝，盘SHA前后完全相同，没有先GC再漏报损坏 |

`remount-r2`另验证65块普通文件unlink后立即SyncAll不会持久化半条回收链；
目录有Detached旧reader时Busy，关闭reader并回收后可删除。两个正例报告目录的
`metadata-checks.json`逐一记录每次重启写回后的生产纯checker Valid结果。
这组测试的host停止发生在SyncAll完成后，保留reader是确定的fixture条件；不能
反向推断原GTK盘当时reader仍存活，原盘只证明Detached节点已持久化且结构完整。

## K7-K06：一次第二重启在Stamp以后失败，原因仍待诊断

- 类别：未解释运行失败，不能标记为已修内核BUG、测试误差或平台限制。
- `build/k7-kernel-remount-r1`的first与reboot1成功，reboot2在3.73s出现panic70。
  失败盘完整分配校验仍Valid，boot serial已从2写成3，因此已过完整元数据检查与
  回收，范围缩小到Stamp完成/最后Flush/hub服务/等待返回；不是K7-K05的flags拒绝。
- 相同kernel/boot/U、相同reboot1输入盘的三次原样重放
  `build/k7-kernel-remount-replay-r1/verification.json`均通过2.69–2.73s。
  新增U内存账本断言的正式remount-r2也完成两次重启。这些不能解释或删除原失败。
- 与成功相比约多1秒，与既有块设备1秒watchdog相容，但尚无分支证据。宿主copy
  未fsync导致guest FLUSH拖慢、迟到PLIC等都仅是假设；没有扩大watchdog、预先刷盘
  或放宽验收来掩盖失败。
- `build/k7-kernel-remount-diagnostic-r1`仅有失败分支编号，宿主构建被主动停止
  以补足诊断，没有进入guest，不算正/负证据。r2快照只在错误路径增加日志，区分
  mount的hub/fs/timer路径，并输出block状态、开始/当前ticks、最后命令/块号、
  IRQbits/usedidx/consumed/PLIC pending；生产源码不含这些调试入口。结果待补充。

K7-K06诊断结果：`build/k7-kernel-remount-diagnostic-r2/verification.json`完成
12次同一输入盘启动，全部通过2.62–2.74s，未进入新增错误分支。因此没有取得
明确根因，不能据此认定watchdog、宿主flush、迟到PLIC中的任何一项已证实。
`comparison.json`确认两份U ELF与原r1完全相同、输入盘SHA相同、原生产文件
全部未改。诊断kernel只用于增加故障信息，不能替代正式生产ELF验收。
原r1/reboot2失败继续保留为未解释的偶发启动失败；若再次发生，应先复用此
诊断快照取得分支与设备账本，不以增加timeout作默认处理。

`build/k7-kernel-remount-evidence.json`汇总此次四个生产delta哈希、修复后ELF、
原盘不变SHA、正负报告与未解释失败路径。完整GTK修复后集成由root在
`build/k7-desktop-r2/verification.json`另行验证，包含重启运行42；本专项不代替
其界面闭环，也不代替独立验收。作者仍未提交，owned生产、tests/tools及本说明
至此停写，等待独立判定。

K7-K06受控I/O对照（仍未取得失败分类）：
`build/k7-kernel-remount-io-r1/verification.json`复用现有诊断ELF和原第二boot
输入盘，交替执行两组各3次。每次两个隔离临时writer，各限4次256MiB写入并对
自己的文件fsync，总负载12GiB、临时工作集512MiB，退出删除负载文件；未调用
全局sync，未操作原盘或其他用户文件，没有调整guest设备watchdog。

- 直接copy后启动：guest通过，分别3.07/3.67/4.26s。
- copy后先对复制盘fsync：guest通过，分别2.63/2.66/3.09s；启动前这次fsync
  另耗0.35/1.08/0.87s。后台一次fsync最长1.36s。
- 记录了每次写入/fsync的起止、guest开始时刻与诊断输出；六次错误分支tuple
  均为空，源盘SHA保持。确实产生了存储竞争且改变了等待时间分布，但仍没有
  观察到同类panic，不能把原r1/reboot2归因为FLUSH deadline或把它算作已解释。
  先fsync组仅为诊断对照，没有被偷偷加入正式验收工具作为通过前提。

## K7-K07：通知语义与故障可观测性（K06接续，尚不等于历史根因）

- 已证实的独立协议缺口：旧block在Idle/Completed收到通知，或Submitted收到
  无新used项的通知时直接失败。Virtio 1.2 §2.7.7.1要求驱动处理spurious notification；
  通知不保证新完成项。修正允许bits0与bits1+Empty保持状态、队列、完成计数和
  原BEGAN；真正的Invalid/head/length/status错误仍致命，1秒watchdog保持不变。
  规范来源：<https://docs.oasis-open.org/virtio/virtio/v1.2/virtio-v1.2.html>。
- 生产增加只在失败时输出的mount阶段/校验分支、hub最后source/pending/enabled、
  block首次失败状态/命令/时间/ISR/used账本/status；观察不消费队列、不claim IRQ、
  不重置设备。故障元组可区分metadata、设备状态、超时和IRQ处理错误。
- `build/k7-block-notification-r3/verification.json`9项通过。旧49b2213和新驱动
  使用相同fixture：真实Read、真实PLIC claim后重放callback的旧版FAIL0a；
  RAM MMIO重复空通知旧版FAIL18；各状态空通知旧版FAIL1f；新版本全部通过。
  新版真实设备完成的head/length/status篡改仍拒绝；RAM模型验证Idle/Submitted/
  Completed下bits0/1Empty不改变状态和完成数、可继续第二请求；重复通知不续期限。
  callback重放与RAM模型不能称为自然发生的重复PLIC IRQ，也不证明原K06起因。
- 可复现入口：`tools/check_k7_kernel.py --case block_notification --compiler ... --out ...`。
  直接验证公开操作结果，不为测试导出驱动可变状态；小fixture不需重编完整内核。

### 诊断自身缺陷与负控

`build/k7-flush-latency-r2/past-deadline`通过QEMU 11.1.1 blkdebug将真实最终FLUSH
延迟1.2秒，已捕获Submitted、command4、used=consumed=195、ISR0、status255及
约1秒watchdog。但旧诊断快照随后读取0x4c001000的PLIC pending时发生S态page fault：
此前只映射了priority/enable/context，遗漏pending页。12次成功启动没有进入错误
路径，不能验证诊断安全性。此缺陷是新增诊断代码的问题，**不是历史panic70根因**。
生产为pending增加单页只读/NX映射，并以显式平台常量引用；需再次执行完整错误分支。

`build/k7-flush-latency-r1`选择第二次底层flush作为注入点，但当前启动只产生一次
实际dirty backend flush，导致延迟未生效，保留为测试装置错误。该目录past-deadline
盘后续被qemu-io写offset0/4096检查装置，verification.json已明确标记，不能用于
验收；原始失败盘与输入盘均未修改。r2失败与新生产revision均另建目录，不覆盖旧证据。

修复后的正式内核为`build/k7-panic-production-r2/build/kernel.elf`，SHA256
`737f4cf3c24aa4cc85753694b3e7a00de595bf74bfbfb0a9a291fce07ea6c650`；
仍为63个VT输入。健康remount的首次运行和两次重启通过；flags1/2/3及65块回收
账本仍成立。`build/k7-panic-recovered-r3`使用同一ELF，原GTK失败盘复制件连续
三boot通过，全部published文件哈希保持，最终163节点/2972块，原件未改。

`build/k7-block-failure-r5/verification.json`在同一正式ELF上通过三种真实后端对照：

| 后端条件 | 精确结果 |
| --- | --- |
| final FLUSH延迟0.5s | 挂载与U账本检查通过，无failure元组 |
| final FLUSH延迟1.2s | `mount.fs`、last phase9、reason7、Submitted、command4、used=consumed195、status255、IRQ0/pending0；elapsed ticks10003691后原panic70 |
| final FLUSH返回EIO | `mount.hub`、last phase8、reason6、Submitted、command4、used196/consumed195、status1；原panic70 |

二者均完整打印后停机，没有二次S态trap。`irq`是失败快照的当前ISR；`notified`
保留最后一次驱动入口看见的ISR，ack后两者可以不同。`phase`是**最后进入的FS
step**，不是实时MOUNT枚举：快速EIO可能在step8提交Flush后、step9第一次执行前
经hub到达，所以合法范围是8/9；command4及status1明确指向最终Flush。元组不是
原子设备快照，错误路径读取期间真实设备仍可能完成请求，分析须结合这个边界。

两次测试装置错误另外保留：block-failure-r3给新remount U套用了旧无ledger输入盘，
已成功mounted boot3之后U返回149；block-failure-r4错误地要求所有EIO的last phase
都为9，但观察到上述合法快速完成交错。r5修正装置配对/断言，未修改生产ELF。
这些不是新内核回归，更不能用来解释历史K06。

复现负控入口为`tools/check_k7_kernel.py --case block_failure --compiler ...
--kernel-from build/k7-panic-production-r2 --disk-from
build/k7-panic-production-r2/reboot1/disk.raw --out <新目录>`。blkdebug使用本机QEMU
11.1.1的`flush_to_disk`事件、`delay-ns`与`errno`；errno0只延迟后正常I/O，errno5
让真实virtio完成携带设备错误。没有修改内核、制造used项、放宽deadline，不能将
受控故障当成自然重现，更不能反向断言历史那次panic就是FLUSH慢。

`build/k7-panic-historical-r1`用同一最终生产ELF与历史K06原输入盘
（SHA256 `e1571b8cfd14ccb98938b8fbecf5add8cd8e55b1543a9d64dc23afeb3efd1b43`）
完成first和两次重启，2.758/2.804/2.614s，9节点/137块，published文件全哈希不变。
专用historical U入口明确检查旧样本target=`new`、orphan消失、Detached计数0，
不要求当时尚未加入fixture的ledger；没有放宽当前remount入口的ledger检查。
原GTK输入盘SHA17a23ce4...82a9与K06输入盘SHA均再次核对保持不变。

### 本轮真实IRQ/取消回收正负对照

- 正控`build/k7-panic-load-cancel-r1/verification.json`：100轮通过，guest99.944s，
  使用相同的180s上限。每轮在真实FS装载Read提交后由U父进程取消，随后真实U外部
  trap才允许hub服务延后的完成。日志恰有100条submitted取消标记；U最后经selector103
  核对`hub::TEST_SEEN==100`。该计数只在hold释放后且USER_TRAPS已增长的真实PLIC
  claim分支增加；没有伪造used entry或软件完成。
- 每轮U同时核对页数、FS节点/块回到原基线，files/request计数0、block状态Idle，
  Child collect为CANCELLED/cause0；100轮完成后总页数再由gate核对。
- 负控`build/k7-panic-load-noirq-r1/verification.json`保留`passed=false`：第一轮
  实际提交并取消后4.634s停机，`runtime.fs`、reason7、command0、used245/consumed244、
  status0、ISR1、PLIC pending64；原1秒deadline后panic73。设备已完成且中断待处理，
  但禁止SEIE后不能靠轮询used ring冒充一次U外部trap。
- `build/k7-panic-irq-comparison-r1.json`严格核对正/负快照仅`kernel/trap.s0`不同：
  resume与idle两处sie掩码544→32（保留STIE、去SEIE）；其他编译输入完全相同，
  两份U ELF逐字节SHA相等，source_inputs在observer之前亦完全相同。负控预期失败
  与正控成功共同构成通过，不改写负控报告为成功。
- 两者是**生产r2派生的调度观察快照**，并非生产ELF；完整桌面与旧盘重启证据使用
  未改动的正式r2 ELF。scope明确区别真实硬件路径、callback重放及RAM模型。

截至本轮，确认的协议缺口和诊断页映射缺陷已经修复并有区分性证据；K06历史单次
panic仍无法绝对归因，不记为“已证明由spurious通知/慢FLUSH导致”。生产、tests/tools
与本说明停写，交独立验收；未提交，不自行把K7节点标为已接受。
