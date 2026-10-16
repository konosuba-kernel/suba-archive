# I 只读预审（不是正式 A 验收）

验收者 `/root/k0_acceptance`。I 未冻结，此文仅为探索反馈，不接受 I 或整体 K0；未修改任何受验实现。阅读了入口、机器包装、S0、清单、boot fixture 与观测工具及 r2 的三例运行记录。期间作者补充 panic reason 与无栈 scause/sepc/stval 输出，已复查最新源码。读取身份见 [inputs](I-preflight-inputs.json)。

## 冻结前应处理

`tools/check_kernel_entry.py::observe` 在见到 marker 后立即终止被观察进程，将 marker 标为 `observer_stopped_halted_vm`。这证明代码走到打印位置，不能证明其后已停机；紧随打印的错误路径可被观察者杀掉而遗漏。独立区分负控打印成功标记，50ms后打印禁用panic，现工具返回 passed=true 并只收到前缀；记录见 [delayed failure](I-preflight-observer-delayed-failure.json)。建议在首次标记后继续有界稳定观察，拒绝禁用输出或进程自行退出，并精确记录“观察到标记、观察者主动终止”，不将标记本身等同 WFI 停机证明。机器停机证据仍要结合实际 S0 无返回路径；有限静默不是永远停机证明。

旧 `panic(reason)` 不输出 reason，坏 BootInfo/错误中断状态/dispatch 无法辨别。作者已在当前源码输出十进制 reason，并为紧急异常打印 scause/sepc/stval；其十位 u32 缓冲和16位hex循环范围成立。这项已在源码层解决，最终须用新组合 E3 运行且坏magic要求准确reason，而非任意panic。

## 窄入口范围与后续合同

当前 BootInfo 检查先限制512字节指针在stage0窗口再读，采用减法边界避免不可信加法溢出。end、DTB范围、单reservation的窄条件在明确固定平台假设下成立。没有保留调用者栈/boot动态对象引用；无普通进程或页表声称。DTB fixture只检查头magic/总长并复制，不解析reserved-memory或完整FDT；BootInfo保留零字节、CRC与完整reservation语义也尚非通用validator。最终文档应显式保留这些限制，不能以valid_info名字或bad-magic一例声称完整BootInfo校验。

机器S0以有限UART轮询、无返回halt、无栈紧急输出支撑K0可信故障路径；没有完整TrapFrame保存/调度。UART假设固定可访问MMIO，硬件失败可能丢失诊断，文档已有best-effort范围。boot是测试fixture、QEMU loader预装kernel，不证明磁盘stage0、正常重启、内核重建发布或suba内编译器运行。

正式 A 仍待当前候选冻结与最终组合E3/自举、profile、S0、host及真实入口记录全部就绪。
