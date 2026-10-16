# K5-r1 独立验收

结论：**通过 K5 功能与生命周期验收**。没有发现需要阻止本阶段提交的生产缺陷。此结论不代表交互性能目标已经达成，也不代表 K7 编辑、保存、编译闭环已经交付。

候选为 `K5-candidate-r1.json`，SHA256 `7d86276770c2d6b64c0a2df1edf696836640c38a5f8917e7abafa255e602442b`；基线为 `10de32fdd5f225c62fb6c90b699122d36bbee4dc`。52 个 owned、120 个 input、20 份作者证据报告的身份全部吻合。编译器为 C64 `e3.elf`，SHA256 `22d2c81fd0dbfc6de6b3b13fb2f485b1c64913849d9e59eeabe8c2757d27ebf4`。

独立执行者 `/root/k4_finish` 完成 fresh-disk GTK、合同、生命周期、队列、旧实现负控及 RAM copier 测试后因额度限制退出，未留下最终判定。`/root/k4_review` 接续静态审查、原始证据与冻结身份核查，并再次执行精确生产 usercopy copier，负责本报告的最终判断。两位均未参与 K5 生产实现。候选中的 reviewer 字段保留原冻结记录，由本报告补充继任关系；未修改候选或任何 owned/input 文件。

## 范围与依据

依据 `design/IMPLEMENTATION.md` 的 K5 节点、`design/CONTRACTS.md` 的窗口/退出合同、`CODE_STYLE.md`，检查实际设备输入、重叠窗口、移动/焦点/关闭、死循环应用强杀、表面撤销及完整回收、事件溢出恢复；同时检查共享调度、usercopy、请求取消、进程退出和 K4 存储接入的影响。

表面“立即回收”按当前明确合同解释为立即撤销访问权、分片释放物理页、退出发布等待账本归零。没有把异步页释放说成单次 syscall 释放全部页。30Hz 是上限，不是已测得的帧率。

## 独立执行与结果

工作目录为 suba；以下命令及其展开后的 QEMU 参数、磁盘、ELF 身份保存在相应目录。`replay.py` 的输出目录不允许覆盖，重现时应使用新的 build 目录。

| 执行 / 证据 | 结果与判别内容 |
| --- | --- |
| `python3 build/k5-independent-r1/replay.py gtk` | 私有 Xvfb 中真实 QEMU GTK/XTest 键鼠，fresh disk；8 步通过，总计 14.82s。重叠、提升/焦点、按键按下与松开、拖动、合作关闭、无响应关闭、Ctrl+Alt+Esc 强杀均有可见帧。最终 free=123997、surface=0。QMP 仅观察画面，不代替此项 GTK 输入。 |
| `python3 build/k5-independent-r1/replay.py contracts` | 非法窗口尺寸/配额、越界与跨未映射页矩形、伪造 Desktop 权限、陈旧句柄、重复创建销毁通过；普通应用写 display 映射仅终止该应用。最终 free=123991、surface=0。 |
| `python3 build/k5-independent-r1/replay.py lifecycle` | 102 轮、52.75s。首轮 CopySurface 已交付部分后撤销源窗口，返回 BadHandle/value=0；第二轮 Dying 的仍存活窗口被 kill，保持已有退出码42；另100轮实际更新、复制、kill、collect，像素、代数、陈旧身份及页/流/窗口列表基线通过。 |
| `python3 build/k5-independent-r1/replay.py queue` | 100 个实际 QMP key edge、14.74s。用65537字节流写阻塞保证窗口队列真实溢出；InputReset、Focus、CloseRequested 顺序与粘滞状态保留，陈旧布局/焦点版本及重复序号被拒绝，退出后资源恢复。 |
| `python3 build/k5-independent-r1/replay.py negative` | **原始顶层 passed=false 保留**；旧 DesktopKill 明确依次输出 COPY REVOKED、DYING LIVE WINDOW、panic23。固定版与旧版两个用户 ELF 完全一致，旧版仅移除 Dying/Exited 状态分支。该项判定为“预期反例成立”，绝不作为生产正例。 |
| `python3 build/k5-independent-r1/check_usercopy.py` | 精确复制当前 `kernel/usercopy.vt` 的 RAM copier；8×8 种地址对齐、14 个长度至4096字节、8192字节 oracle/canary/源保持检查通过。 |
| `python3 build/k5-independent-r2/audit.py` | 继任者重新核对全部冻结身份、4份关键快照、28个ELF/启动输入/固件身份、8幅GTK帧哈希；再次 `qemu-riscv64 build/k5-independent-r1/usercopy/check.elf` 返回0。全部通过。 |

负控包装器存在一个测试报告缺口：`require` 抛出 `ValueError`，而独立 `replay.py` 只捕获 `AssertionError`，因此不会写入其预期的 `expected_failure` 字段。最终判断直接依据原始 panic23 日志、精确源差异及相同用户 ELF，记录在 `build/k5-independent-r2/verification.json`。未覆写旧 false、未把异常退出改装成生产通过。

## 静态审查和证据适用性

- Desktop 权限绑定唯一 boot Prepared 进程身份与句柄，普通 spawn 不继承；常规 File/Stream/Job 分派不把 Desktop 当成其他对象。普通应用没有 framebuffer 映射。可信桌面自身错误仍可停机，符合可信组件范围。
- Window 从 Creating/Prepared 到 Live，再到 Dead/Empty；发布才建立句柄引用。取消创建、关闭、进程退出都进入同一回收路径。Dead 身份立即禁止访问，槽复用递增代数；进程退出发布等待窗口及 FS 清理完成。
- Surface 请求只保存身份、偏移和用户地址整数；完整用户范围先验证，每片重新验证身份；最多2KiB及页边界限制，没有跨等待裸借用表面页。部分失败返回值要求调用者丢弃整个局部快照；桌面在 render 失败后刷新列表并重新标记损伤。
- 输入 IRQ 在 drain 前 ack，最多处理64个完成项；复用已接受共同 transport，未改其环索引/屏障实现。原始及每窗口队列的 reset 优先于普通输入，focus/close 不会被普通队列溢出挤掉；路由必须匹配布局、焦点与一次性序号。
- 共享 usercopy 保留整段地址与逐页权限校验，新增 usize 路径只处理已验证的普通 RAM 物理别名和内核缓冲；精确 copier 的独立4096字节测试补足作者2048字节范围。
- 调度每批最多32个片，片间服务 IRQ，时间检查控制是否继续下一片；没有把1ms检查阈值当作单片硬上界。窗口页回收轮转且有界。K4 `worker` 的空清理扫描跳过及共有请求路径仍有真实存储回归证据。

关键桌面/合同快照 SHA256 为 `9c55cb14c300d8afaf68608c284fe464c16d79b187bcc648d425a80bd696cecb`，与冻结生产源码的差异仅为额外启动 fixture、输出基线/回收账本。生命周期/队列快照为 `77f948456f294c0f166e6f9b628cf519afb0f47a683f1e7f00858ae3290e7e80`，仅增加两个明确的调度交错控制；其余100轮为普通用户调用。继任验收者重新从冻结源码生成预期 observer 源文本并逐项核对，不只相信报告中的 passed 字段。

作者最终 `k5-storage-filesystem-r2`、`k5-storage-boundaries-r1`、`k5-storage-cancel-dma-r2` 源输入与冻结候选吻合，均两次启动通过；DMA取消每次启动100轮并检查实际 IRQ 与资源恢复。本次独立验收核查这些作者证据，不冒称另外独立重跑了存储长测；共同 transport 和 K4 既有验收仍作为依赖保留。旧构建超时记录、旧桌面光标遮挡像素断言失败记录不抹除、不作为最终正例。

旧 `k5-devices-private-r1` / `k5-overflow-r1` 仅 `tests/k5/gtk_input.py` 与冻结输入不同，生产 input/display/transport 一致；裸 S 溢出工具不调用该 GTK helper。其证据限定于真实驱动输入/原始队列溢出，受保护桌面的完整 GTK 行为以本次 fresh 8 步记录为准。

## 保留边界与后续工作

1. **秒级重绘仍是明确性能欠账。** 独立 GTK 可见帧等待约1.58–2.37s；全流程14.82s。不能声称100ms交互目标、30fps或两个编译任务背景下的p99已达标。部分关闭步骤计时很短也不构成端到端延迟证明；后续 K7/K10 必须继续测量和改进。
2. GTK 在私有 X11/Xvfb 上实际运行，证明该 GTK 输入路径；不扩大为任意宿主窗口管理器、键盘布局或 Wayland 环境兼容保证。
3. QEMU 对超过设备队列容量的整帧输入可能无 SYN_DROPPED 地丢弃；guest 只能保证可观察的设备/软件溢出恢复，不能宣称检测不可观察的宿主丢失。
4. 当前应用仍由明确 RAM fixture 装载；编辑器、字体在桌面中的集成、FS 应用装载、Job 编译/保存闭环属于 K7。未借本报告提前验收这些范围，也未重做完整 K10 压力矩阵。

本报告可解除 K5 对 K7 的功能依赖；提交仍应精确包含候选 owned 清单、候选及本验收报告，并保留上述性能和范围限制。
