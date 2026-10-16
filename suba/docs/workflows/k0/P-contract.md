# K0-P 固定 profile 与有限桥合同

2026-10-14，候选设计；测试与冻结身份见 P-r1.md / P-candidate-r1.json。

编译器新增 `bootstrap::target`：四个枚举profile选择唯一 `Layout{profile,base,window,stack}`。目标布局与编译器宿主服务无关。运行在Linux上的编译器可以输出任一profile。`input` 在一次编译开始重置并从清单选择，后续入口、重定位和ELF布局只读此记录。现有内部后端探针默认Linux布局。

| profile | text起点 | image总窗口 | 编译器预留机器栈 | entry普通安全函数签名 |
|---|---:|---:|---:|---|
| linux-user | 0x10000 | 64 MiB | 无，Linux提供 | `()->u32` |
| suba-user | 0x10000 | 64 MiB | 无，loader提供 | `()->u32` |
| suba-boot | 0x80200000 | 2 MiB | 128 KiB | `(hart:usize,dtb:usize)->u32` |
| suba-kernel | 0x80400000 | 64 MiB | 128 KiB | `(info:usize)->u32` |

三段仍为RX/R/RW，不增加低地址header段；ELF header位于未装载文件前缀。机器profile入口是最低PT_LOAD的第一个字节，等于e_entry。image::finish按相对base的偏移对齐，不能把高物理地址传给只接受64MiB内偏移的align函数。指令PC-relative和静态ABS64修补共同使用该布局。整个RW内存范围（初始化数据、BSS、栈）计入窗口。

清单保留 `entry module::function`。新增的bind仅以下两种两词形式（等号内不得有空格）：

```
bind panic=module::panic
bind trap_dispatch=module::dispatch
```

- `panic` 仅boot/kernel，必需，安全普通函数 `(reason:u32)->u32`。启动函数返回不当作正常退出：reason=102；语言checked panic为101。panic函数返回后，将其u32结果放a0尾跳到S0固定终点 `__suba_halt`。
- `trap_dispatch` 仅kernel，必需，安全普通函数 `(frame:usize)->usize`。编译器定义 `__suba_trap_dispatch`，S0可以call此符号；该桥尾跳至绑定普通函数。入a0=frame，返回a0=待恢复frame。尾跳保留原ra，S-next普通函数按现有C标量ABI保存/恢复自身使用的callee-saved寄存器。桥本身不保存被打断现场，不配置trap CSR，不切换栈。
- 用户profile拒绝所有bind，boot拒绝trap_dispatch。重复/未知角色、缺少必需绑定、extern/unsafe函数或错误参数/结果类型都拒绝。没有任意export、函数地址值或外部linker。
- `__suba_halt` 必须由机器运行库的S0定义且不得返回。缺少定义产生E_LINK，重复定义拒绝。
- suba-user正常返回和panic都尾跳 `__suba_exit`（a0=退出码，panic101），必须由suba运行库提供真实syscall且不得返回；不会继承Linux exit syscall。当前P测试只链接无限循环占位以验证用户布局，明确不把它当suba运行库。

机器入口在使用任何旧栈前清除sstatus.SIE；保留a0/a1，用x5/x6/x31清零整个BSS半开区间，随后把sp设为新增BSS栈对象末尾，16字节对齐，并置x27=0。清零包含栈；不使用旧sp，不依赖loader已清BSS。内核安全普通函数不保存引导栈引用。128KiB是K0初始运行栈；guard、页表和独立panic紧急栈属于K2，未在此声称实现；也未证明整条调用链的最大栈消耗。

Linux继续令x27=初始sp，suba-user令x27=入口a0的只读参数块地址，保留loader提供的sp。普通调用/extern须保持x27；完整trap保存x1–x31和CSR是K2机器胶水的责任。FP/vector、嵌套trap与进程隔离不是本节点。

image为BSS边界创建匿名内部符号，用户S0不能指定其名字；stack同为匿名BSS对象。trap固定符号仍可被S0重复声明，但会被现有一次定义检查拒绝。有限桥是链接胶水，安全性依赖可信S0遵守其调用合同。

`main` / `input` 已按H合同转向runtime::host；保存阶段文本来自宿主后端，保留四行为修复的错误与残留信息。P不修改host实现。现有工具若单独编译input/image/rv64，需要显式纳入target源；编译input还需host后端，不能用隐藏自动导入弥补清单缺项。
