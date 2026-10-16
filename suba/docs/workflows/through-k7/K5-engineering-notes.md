# K5 探索工程记录

2026-10-15，作者 `/root/ram_fdt`。这些是正式K5之前的设备探针，不是K5候选或独立验收。未实现受保护desktop、窗口生命周期和完整IRQ集成。原始输入/产物位于 ignored `build/through-k7-k5-draft/`，清单 `evidence.json` SHA256 `44b698acb8904ec4b99b2f369a22ac97a45d8f71b3e10ad7f1dd2265dc6ad289`；详细协议来源和命令见该目录README。生产仍等待K3和C64接受及K4共享transport冻结。

## QEMU 会静默丢弃无法完整容纳的输入帧

- 症状：A-down已到guest；QMP随后发含A-up及64个B边缘的一批，整批没有进入guest；下一批C-down正常抵达。A-up画面标记缺失。
- 复现证据：`oversize-r1/run-oversize.py`、serial.log、qmp.json、frame.png；guest用真实virtio-input队列，不用qtest或host改内存。
- 已确认原因：QEMU按SYN_REPORT聚合帧；描述符不足时撤回已取描述符并丢弃整帧，不保证发出SYN_DROPPED。空队列也无法容纳超过64条的帧，因此只检查used已满并不能完整检测丢失。
- 处理状态：保留平台限制；固定QEMU/GTK视为可信输入源，正式K5保证guest软件队列溢出及可观测设备丢失会InputReset。正常QMP验收使用容量内的普通帧，这不是对超大批问题的修复。暂不引入按键租期，以免破坏合法长按和修饰键；若正常GTK/正常速率也复现卡键，再据实改进。
- 启示：必须区分设备不可观测丢失与本地可观测队列满；不能用同一个overflow计数器假装两者都已恢复。此处是平台协议限制，不归因于S-next编译器。

## 有界操作仍需要时间预算

- 症状/证据：真实设备一帧63个键事件加SYN，队列64；`budget-r1`实际drain校验used/id/len、复制512B至内核私有RAW、回补descriptor并notify/ack，用7818个10MHz ticks，即0.7818ms；下一帧2事件0.0655ms。
- 已确认：keyboard/tablet的eventq和statusq QueueNumMax均64。正常QMP键边缘帧2条、X/Y/button合并帧4条。GTK探针观察30个指针帧，每帧3条。64槽只容21个这种指针帧；1000帧/s下约21ms是容量算术，不是已测最坏输入速率或实时保证。
- 处理状态：正式实现先复制8B到内核拥有状态并立即回补，再唤醒用户桌面；不能等应用消费或绘制。最长SIE关闭区间（尤其usercopy）仍需实测；K3采用4KiB内部搬运片。此探针轮询，没有证明外部IRQ延迟。
- 启示：字节/迭代上限与交互延迟是不同合同。消费者的内存复制片大小要结合队列容量和实际时间，而不是只看64KiB ABI最大长度。

## 绘制成本与编译器能力边界

- 症状/证据：`input-r1`逐像素判断两个矩形并写1024×768前缓冲，一次约0.5166s；`input-fast-r1`改为普通S-next切片写约0.5469s，并未改善。两次是具体host上的单次探针，不能当稳定性能比较。
- 已确认：这个朴素全屏循环没有达到30Hz；由实证不能确定耗时主要属于代码生成、边界检查、分支还是探针结构。
- 处理状态：正式桌面采用损伤合并、裁剪行/跨度、有界分片、落后时丢中间帧，绘制放可抢占U态；30Hz是刷新上限。完整合成时间和像素拷贝量留待正式测量。
- 启示：先测真实算法，再决定语言/后端优化；此次没有因此引入编译器优化或把渲染塞入不可抢占内核。

## S0 半字读取与队列索引原子性

- 症状：探索使用`lhu`被当前S0以I_UNSUPPORTED拒绝，记录input-compile-r1.log；探针临时用两个lbu代替。
- 已确认：两个字节读取并不等价于共享队列索引的原子16位读取，尤其在回绕附近。不能把探针替代方法直接搬进生产。
- 处理状态：K4共享transport探索已采用一次aligned16位store发布idx，aligned32位读取后取高16位读used.idx，并报告实际IRQ回绕测试；正式K5等待其唯一owner冻结接口，不复制通用transport。本记录不替K4独立验收背书。
- 启示：机器边界缺少某条指令时，要先用已有宽度表达正确的访问语义；扩充语言指令表不是唯一方案，但拆成两次访问须审查原子性。

## GTK 探针只验证了指针路径

- 症状/证据：`gtk-r1`使用真实GTK后端和合成X11输入，guest记录了指针帧，但键盘及按钮画面标记未出现。正常QMP输入的相应标记已在`input-r1`出现。
- 已确认：当前GTK探针未证明完整键鼠路径。没有证据判定是测试焦点/窗口选择问题还是其他输入路径问题，不称为已定位驱动BUG。
- 处理状态：保留未通过范围；正式K5仍须实际GTK与QMP可见交互验收，不能用QMP成功覆盖这一缺口。
- 启示：分层测试必须标明进入系统的位置；QMP输入、GTK事件、物理人工操作不能混称同一种端到端证据。

## 正式实施接续（2026-10-15，作者 `/root/k5_windows`）

前文是旧探索阶段的原始记录；当时的“等待”状态不适用于本节。现已接受 K3 `6162887`、C64 `bd73055`；共享 transport 候选 `fd2845d4…0ac` 已由 `/root/k4_acceptance` 独立核验通过，正式输入驱动仅消费该实现。K4 尚在实施，因此 K5 的共享核心接入只写入 ignored 快照，不改 root 持有的生产文件。

### E06：不一致的并行构建输入属于测试组装错误

- 首次 `build/k5-modules-r1` 从正在编辑的共享 K4 文件逐一拷贝，遇到 `fs/state.vt` 已引入 `suba::files` 而当时复制的清单未包含其定义，编译报 E_NAME。
- 未将此结果归为语言 BUG，也未改 root 文件。改用成功编译的 `build/k4-production-mount-r1` 静态快照叠加 K5 文件；K4 提交后再由 root 做语义整合。
- 启示：并行编写互斥文件不代表消费者可以无版本地取整个工作树；构建必须固定依赖快照。

### E07：opaque Queue 不能由外部 zero 构造

- `build/k5-device-r1/compile.log` 报 `E_NAME file=5 byte=3799`，定位为 `var event: virtio::Queue = zero`。Queue 的字段由 transport 私有，拒绝构造符合语言封装规则。
- 输入初始化改为沿 `QueueRead::Ready` 的成功分支传递已验证的 queue，分别完成 status queue 与发布；未开放私有字段、未新增未初始化状态。`k5-device-r2/compile.log` 构建成功。
- 启示：具体返回枚举有利于保持构造证明；需要两个已验证 opaque 值时，命名准备阶段比引入零值占位更清晰。错误应最好指向“私有类型构造”而不只有 E_NAME。

### E08：GTK 键鼠缺口已有实际补测，但不臆断单一根因

- 保留旧 `gtk-r1` 仅指针通过的事实。新 `build/k5-device-gtk-r1` 使用同一正式驱动 ELF（`k5-device-r2/probe.elf`），为该 QEMU 进程显式设置 `GDK_BACKEND=x11`，raise/focus 窗口并先点击客户区，随后 XTest 发键鼠。没有通过 QMP 注入这次键鼠；QMP 只取屏。
- serial.log 实际包含 evdev A(30) down/up、绝对指针和左键 down/up，IRQ 计数有增长；屏幕通过同一 ramfb BSS 显示事件标记。先前缺失的键和按钮路径已在该配置下观察到。
- 本次同时改变后端选择、抬升/聚焦和客户区首次点击，尚未逐项消融，故不能把某一项断言为旧失败的唯一根因。已证实的结论是明确的测试配置成功；不是物理人工硬件输入证明。
- 此证据仅覆盖裸 S 驱动探针，平台 MMIO alias 在测试快照设为零；保护桌面、U映射、生命周期和完整 K5 仍需后续集成验收。

### E09：窗口堆叠代数需独立于槽复用

- 静态检查发现仅用槽号作 rank 或“新建取最大 rank+1”，若销毁不压缩排名，会在多次关闭/新建后产生洞或重复 rank，导致 compositor 排序无法覆盖全部窗口。此问题在首次完整桌面运行前发现，无实机故障声明。
- revoke 对仍存活且高于旧 rank 的窗口减一；新窗口从有界排名尾部发布；raise 在同一个 owner 内压缩原位置。身份 generation 不参与 z-order，不因重排变化。
- 后续测试需循环创建/销毁/抬升并检验排名与可见窗口，不只测试最初两个窗口。

### E10：GTK readiness 不等于 guest 驱动 readiness

- 可复现补充：`k5-devices-verified-r1/verification.json` 保留 failed，QMP 路径通过，紧接启动后的 GTK 测试没有任何 guest 输入，像素断言失败；没有因此忽略 GTK 断言。
- 测试给 GTK 的首次窗口 map/focus 事件一个 1 秒稳定期（guest READY 可能更早），不改驱动；同一已编译 ELF 的 `k5-gtk-repeat-r1..r4` 连续 4 次均得到完整 A/按钮边缘和三处准确标记像素。正式测试同时保留显式 X11 后端及 focus/click 条件。
- 这支持“测试窗口就绪时序”是一个相关因素；尚未证明任意宿主负载下 1 秒充分。最终桌面测试应等实际窗口映射和应用可见状态，保留失败，不以固定睡眠当核心正确性证明。

### E11：input IRQ 应先 ack，再有界 drain

- 静态并发审查发现原输入 drain 在最后一次 take 返回 Empty 后才 ack。设备可在 take 与 ack 之间写入新的 used entry，并置 ISR；晚 ack 会清掉此通知，留下无人继续读取的事件。
- 改为先确认本次 ISR，再最多取64项、及时回补，最后kick；处理期间新增完成保留其新的 IRQ level，由 PLIC 下次 claim 继续推进。block 的单请求时序不推导为输入持续补充队列的时序。
- 此潜在丢唤醒在审查中发现，尚无对应旧实现实机复现声明。后续用持续速率输入和 drain 边界注入观察剩余队列，不仅验证一个按键。


### E12：逐片后台调度把忙应用量子放大为几十秒合成延迟

- `k5-protected-r3` 和 `k5-interactions-r1` 的初始 30 秒仅背景，不能算窗口交付。
  `k5-protected-debug-r1` UART 确认两个 CREATE/PUBLISHED；`k5-desktop-debug-r1`
  在 U framebuffer 末行记录只读进度：30 秒时 LIST=2、copy status=OK、row=180，
  首个含窗口的帧尚未 present。观测源码和失败截图保留在 ignored build 目录。
- 已确认：每次 schedule 仅一个后台 step，然后可回到 busy 应用执行10ms；
  reaper/child/request 公平分摊又放大了每片代价。64KiB请求仍按2KiB/行/页
  边界推进，合成两窗口需数百片。工作有界不意味着前台等待延迟可接受。
- 处理：完整紧密行允许跨行合并 span，仍不超过2KiB且不跨任一页；共享调度器
  的有界后台批次改进交由 root 集成，以便同时改善K7编译期间的文件/窗口进度。
  没有扩大复制片、没有绕过用户保护或降低测试期望。
- 启示：分片上界与调度吞吐必须一起设计；只测所有进程阻塞时的吞吐会漏掉
  一个持续可运行进程对后台工作的干扰。正式门禁需要忙应用与交互并存。


### E13：RAM字节搬运可用现有语言表达对齐快路径

- `window_surface` 的2KiB搬运及 U draw 的逐像素组装，改为源/目标同余mod8时
  前缀字节、对齐usize、尾字节；不同余保持字节fallback。只用于明确有效的普通
  RAM，未引入内联汇编 memcpy、未用它访问MMIO或代替user range验证。
- `build/k5-ram-r1` 对生产私有 copier 的原样源函数做64个对齐组合×12长度
  的字节 oracle/canary/source不变测试；draw另测裁剪、行padding、奇数宽度；
  Linux/RV64原生执行通过。完整保护内核的成本对照仍以交互记录为准，不能从
  微测试推断最终桌面速度。共享usercopy快路径仅在 ignored snapshot 试验。
- 第一个测试清单误写 `linux-rv64`，编译器按不支持profile拒绝，改为已有
  `linux-user` 后通过。这是测试清单错误，不是语言新增需求或编译器BUG。

### E14：宿主 Xwayland 的 XTest 入口需要隔离验证

- `k5-devices-r3` 的 GTK 再次只有移动、没有键/按钮；已检查 X11 window mapped
  和 X focus，不能继续把问题简单归结为“等1秒”。`k5-gtk-isolated-r1` 在独立
  kwin virtual + Xwayland 会话没有任何guest事件，compositor记录libei的
  `EI_EVENT_SYNC` unhandled。该日志仅说明测试入口异常，尚未逐层定位全部根因。
- `k5-gtk-xvfb-r1` 采用独立 Xvfb，同一 QEMU GTK、同一driver ELF、同一XTest
  注入全部键/按钮/指针边缘通过。QMP只读屏幕，没有替代键鼠注入。此配置隔离
  宿主真实桌面焦点及Xwayland输入转发；不宣称物理人工键盘验收。
- Xvfb从[Arch官方包信息](https://archlinux.org/packages/extra/x86_64/xorg-server-xvfb/)
  取得版本21.1.25-2，经本机Arch keyring签名验证后仅解包到 ignored
  `build/k5-xvfb-runtime`，未系统安装；source.json、signature.log保存身份。
  初次本机旧pacman数据库给出的21.1.24-1镜像已404，保留为测试依赖获取问题。
- 正式驱动测试新增 `--xvfb /path/to/Xvfb`；它只影响宿主测试环境，不成为suba
  运行依赖。真实GTK仍按实际路径执行，不用虚构通过或删去原失败。

### E15：完整GTK测试不能在等待慢帧时无意制造按键重复

- `k5-gtk-desktop-r1` 通过重叠、焦点、键下后，键上颜色等待超时。该测试在等
  “按下色”变得可见期间一直让宿主键保持按下，默认X11 autorepeat会让这个
  单边缘测试变成持续重复输入；原示例也会为每个重复值重画整个窗口。
- 保留该失败，尚不把它单独归因于driver丢键。私有X11的单边缘门禁显式用
  `-r`关闭宿主自动重复，测试所发送的边缘因此可数；应用fixture则按pressed
  状态去重相同重复键，并在InputReset时清除状态。这是消费者义务，不能靠
  宿主测试设置替代。后续完整GTK重跑仍需通过。

### E16：桌面强制终止快捷键遗漏

- 预审对照 ARCHITECTURE §6 发现 Ctrl+Alt+Esc 尚未实现，原 `event_one`
  将所有键直接转发。鼠标右键强杀通过不能替代已承诺的键盘逃生路径。
- 增加左右 Ctrl/Alt 独立 bit 状态；按下 Esc 且两类修饰键存在时终止当前焦点
  应用，InputReset 清除修饰键，释放一侧不抹掉另一侧。真实 QMP/GTK 门禁末步
  改为快捷键；其新证据必须单独通过，不能沿用旧右键测试的通过结论。

### E17：集成脚本的穷尽 match 不能替代错误语义审查

- ignored `integrate.py` 曾统一插入 `Desktop => {}` 以补齐 Object match。
  file/stream/spawn Job 参数位置必须明确返回 BadHandle；空分支可能继续使用
  零身份。root 在正式接入前逐处修正，未在运行生产内核触发，不记作已复现漏洞。
- 后续生产证据以 K4 commit `10de32f` 加冻结源码输入哈希为界；旧探索 snapshot
  不等于最新核心集成验收。

### E18：CopySurface 的主要等待来自 busy U 量子和空调度轮次

- 原 fence.i 保留、相同对齐 RAM copier、跳过空 window/child 轮次的对照：
  `k5-profile-interactions-r1` 固定10ms U，总49.02s，首帧3.95s，焦点9.98s，
  key-up12.30s；`k5-profile-adaptive-interactions-r1` 仅有可推进后台工作时1ms U，
  总14.77s，首帧1.59s，焦点2.12s，key-up2.89s。均含忙循环应用，两应用回收
  后页面账本返回124155、surface=0。秒级交互仍需要进一步分析，不等于体验合格。
- 固定策略94次Copy/4614非空片：copy1.202s、请求存续43.086s、调度9195次、
  其中U37.389s；自适应96次/4638片：copy1.138s、存续9.426s、调度9173次、
  其中U3.633s。请求数量略差来自输入与刷新时序；独立计数证明主等待在U量子。
- publication-only fence.i 对旧word快照总耗时93.10→90.78s，收益不足以归因为
  主要瓶颈，生产保留原同步语义。32片/1ms为“继续批次阈值”，最后一片可超出；
  实测profile最大单片5.36/6.57ms，不能宣称严格1ms上界。

### E19：退出与 DesktopKill 的可达间隙导致内核 panic

- 预审发现普通SYS_EXIT/fault先把owner标为Dying，Cleanup::Cancel稍后才撤销
  窗口。此时桌面可仍取到Live窗口；旧DesktopKill调用terminate(Dying)返回false，
  再升级为panic23。这是确定可达的状态机错误，不能把已退出应用当成内核不变量破坏。
- 修复：Dying/Exited分支立即撤销窗口并幂等成功，保留原exit status/cause；
  Vacant返回BadHandle。新增确定性调度fixture在检查owner状态前模拟已发生退出，
  并验证原status42最终被collect，另在CopySurface第一片后撤销验证部分结果丢弃。
- 旧版失败、新版通过证据仍须分别执行；仅静态解释不冒充实测。

### E20：测试源必须遵守当前 S-next 常量边界

- lifecycle-r1 的新U fixture用结构体常量保存矩形，编译报
  `I_UNSUPPORTED file=10 byte=555`。当前语言没有该const初始化承诺，改为返回
  结构体值的普通函数，独立用户程序编译通过。这是fixture误用，不是编译器回归。
- 首次kernel已成功编译，保留失败记录和原U源码，补记录冻结输入哈希后供r2
  精确复用kernel；不把修正文件覆盖回旧snapshot，也不清除旧诊断。

### E21：队列门禁需要背压屏障，不能靠固定等待模拟“不消费”

- `k5-window-queue-r1` 在已发送100键边缘后以fixture code27失败，耗时15.63s。
  原普通应用仅等待10秒就开始消费/退出；并发编译、调度与多次路由检查使这个
  时间假设不足。未记录当时具体syscall status，不能据此宣称driver丢键或内核BUG。
- 改为普通应用向容量65536的stream写65537字节；桌面只有完成100次路由才开始
  drain。消费者由实际背压阻塞，何时释放由协议决定，不依赖宿主快慢。
- `k5-window-queue-r2` 通过，15.31s：真实QMP100个独立键边缘全部路由；同一事件
  先用过期layout/focus均Busy，再用正确版本成功，重复sequence再Busy；窗口首三个
  事件按顺序为Software InputReset、Focus、CloseRequested。最后collect并核对空
  window list、free-page基线与stream=0。固定内核与lifecycle-r2精确复用。

### E22：快捷键终态像素不能被测试自身光标遮挡

- 正式GTK `k5-integrated-desktop-r3` 已观察忙应用退出、surface=0与页面归基线，
  但最后背景断言等待90秒失败：测试用(100,100)聚焦后把光标留在同一采样点。
  root核对PPM该点为白色光标，相邻(110,110)/(90,100)和(500,250)均为背景。
- 保留r3失败与终态图，聚焦后移动到(800,600)再发Ctrl+Alt+Esc；背景颜色断言不放宽。
  同一冻结kernel可重新跑实际GTK输入，无需更换guest或编译新内核。

### 当前新增边界证据（仍需独立验收）

- `build/k5-lifecycle-r2`：102轮通过，67.45s。前两轮分别在CopySurface至少首片后
  撤销、以及在DesktopKill检查前置Dying；第二轮collect保留status42。余下100轮
  逐轮update/copy/kill/collect，完整像素校验、旧identity拒绝、同slot新generation，
  页面数/stream/list均回到同一基线。此snapshot的原始source_inputs与当前生产
  manifest源文件逐项hash核对无差异；仅明确的测试observer在冻结副本内插入。
- `build/k5-old-kill-negative-r1` 在宿主kernel编译阶段240s超时，无ELF、未进guest；
  不能把此失败当作panic竞态复现。新600s编译预算只调整宿主构建工具，未改变
  guest运行期、后台片或交互验收时间要求；negative-r2将再次验证旧实现。

- 修正光标位置后 `build/k5-integrated-gtk-r4` 对同一
  `k5-integrated-desktop-r3` 冻结kernel/users通过真实GTK/XTest 8步，18.68s：
  初始重叠1.87s、raise2.65s、keydown1.87s、keyup3.45s、drag2.91s，关闭与
  Ctrl+Alt+Esc终止约0.013s；free=123997、surface=0。root目视drag截图确认
  两窗位置、焦点条和关闭区。此次只修host测试、未更换ELF。秒级重绘仍是明确
  未解决性能目标，不将功能通过写成流畅交互验收。

- `build/k5-old-kill-negative-r2` 已进入真实guest并确定复现：UART依次为
  `K5 COPY REVOKED AFTER FIRST PIECE`、`K5 KILL OBSERVES DYING LIVE WINDOW`、
  `suba kernel panic reason=23`，工具按失败退出并保留passed=false。旧实现错误
  现在有实测反证，不再只是静态可达性说明；新实现r2通过102轮，另以最终同版
  U fixture在r3精确复用修复kernel复跑，以便正反对照用户ELF一致。

- 最终 `build/k5-lifecycle-r3` 同版对照通过102轮，56.89s；
  两个user ELF与negative-r2逐字节SHA256一致，正反均触发同两个调度observer。
  `regression-comparison.json` 保存对照路径、相同用户ELF哈希、旧panic23和新通过。
