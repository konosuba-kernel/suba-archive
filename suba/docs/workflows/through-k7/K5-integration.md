# K5 接入说明

2026-10-16。共享核心已由root基于K4提交 `10de32f` 接入；本说明是接口记录，不是独立验收报告。

## 所有权与新增输入

新增内核 VT 输入共 10 个：`abi/windows.vt`、`kernel/device/display.vt`、
`kernel/device/input.vt`、`kernel/space_external.vt`、`kernel/space_display.vt`、
`kernel/process_display.vt`、`kernel/window.vt`、`kernel/window_surface.vt`、
`kernel/window_events.vt`、`kernel/dispatch_window.vt`。

`user/desktop/desktop.build` 构建可信 U 态桌面。`user/libsuba/windows.vt` 提供窗口
ABI 编解码，`user/draw/pixels.vt` 只操作调用者拥有的普通 RAM。内核不调用绘图代码。
已有 transport 仅由 input 消费，不增加第二套队列所有者。

## 核心挂接点

1. `objects::Object` 增加 `Desktop(Identity)`；所有不相干的穷尽 match 明确拒绝。
   release Window 调用 `window::release`；release Desktop 无外部资源释放。
2. `request::Operation` 增加 `WindowCreate(Identity)` 和 `WindowCopy(Surface)`；
   `Surface` 包含验证后的 `window::Copy`、`done`、`writing`。
   cancel create 调用 abort；cancel copy 不保留页引用，无额外释放。
3. `dispatch::advance` 分派到 `create_window_step`、`surface_step`。
   `has_work` 包含这两种请求和 window reaper。原子工作片保持最多 2KiB surface
   与最多 2KiB usercopy，不在一个 S 态片内搬完整 64KiB。
4. 进程取消先撤 request，再 `window::revoke_owner`，然后原有句柄 drain。
   Tail 在 `window::owner_settled(id)` 前不能释放进程地址空间（外部页 quota 仍归它）。
   window reaper 每次只释放一页，公平穿插到共享后台调度，不能让 child/FS 饿死。
5. SYS_WINDOW_CREATE..TRY_EVENT 和 SYS_DESKTOP_LIST..62 分派 `window_call`。
   wait 的 Window READABLE 由 `window::readable` 判断；Desktop READABLE 由
   input readable 或 window changed 判断，先验证 boot capability。
6. hub probe 对 device id 18 调 input initialize 并开启其 PLIC IRQ；所有输入设备
   初始化后检查 configured（键盘与 tablet 各一个）。claim 后根据 IRQ 身份分派
   block 或 input，统一 complete。不得把 input 的持续完成时序套成 block 单请求。
7. display 在保护地址空间启用后、指定 desktop 装载前 initialize。唯一指定 boot
   image 经过 `boot_desktop_ready`：逐页借映射 ramfb、安装 Desktop 句柄、将返回
   token 写入 argv[1]、grant trust、publish。普通运行相同 ELF 不获得此权。
8. `process::terminate` 拒绝 trusted desktop；用户 fault 识别为可信程序错误并
   返回内核故障路径；普通 kill_child 在调用 terminate 前返回 Denied。
   desktop 自己退出也停机，不能留下失去输入管理者的系统假运行。

ignored `build/through-k7-k5-draft/integrate.py` 保存旧 K4 mount 快照上的具体改动，
只作语义参考，不能覆盖最新 K4 代码。它额外 boot 两个测试应用的行属于 fixture，
正式启动策略应保持唯一 desktop 入口，应用由正常接口启动。

## 合同需同步的精化

`CONTRACTS.md` §6 原先声称最多64KiB在同一有界步骤 copyout，应改为请求可分片：
开始校验完整 user range，过程中每片重新校验 window generation；窗口失效返回
BadHandle、value=0。调用方丢弃该次请求全部局部像素，不能展示其部分结果。
窗口页从不直接映射给 desktop，无需等待 compositor 归还引用。撤销立即发生，
物理页由公平的一页 reaper 回收；“立即回收”不能解释成一次不可抢占释放768页。

## 验收边界

裸 S input/display 探针只能证明实际设备/IRQ/GTK输入路径。完整 K5 还必须以保护
内核和 U 桌面运行两应用，核验重叠、焦点、拖动、CloseRequested、强杀及回收，
并测试 stale identity、权限拒绝、队列 overflow/reset 和跨页无效范围。实际组合证据见
[K5核心记录](K5-core-notes.md)，独立判定另行记录；READY串口或纯背景截图不能代替窗口交付。

## Protected lifecycle and queue gates

`tools/check_k5_lifecycle.py --mode lifecycle` runs 102 protected child rounds:
copy-in-progress revocation, Dying-before-window-revoke kill preserving status 42,
then 100 normal update/copy/kill/collect rounds. Every round checks empty list,
free-page baseline and stream count; reuse of the same window slot must change its
identity generation. Old identities and stale layout/focus versions are rejected.

`--mode queue --kernel-from <lifecycle snapshot>` reuses the exact observed kernel
and uses actual QMP keyboard input. The trusted test desktop routes 100 individual
edges to an ordinary process withholding event reads behind a stream backpressure barrier.
It checks stale input versions do not consume the current event, routing consumes
it once, InputReset precedes retained Focus and CloseRequested, then collects the
child and checks its resource baseline. Host edge injection is paced 20ms; only after all 100 routes does the desktop drain
the 65537-byte producer write, which cannot fit in the 65536-byte stream buffer.

The two scheduling hooks are frozen source-only test observers calling ordinary
terminate/revoke state transitions; they never change ELF bytes or grant ordinary
apps desktop authority. `--reproduce-old-kill` removes only the Dying/Exited fix
from that snapshot for the expected panic 23 negative control. It must fail and is
never a production candidate. All output folders retain logs, frames, commands,
compiler/kernel/input hashes and pass/fail records.
