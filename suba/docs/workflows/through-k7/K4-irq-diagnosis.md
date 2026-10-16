# K4 指定 DMA 完成通知的诊断

2026-10-16，root。此文记录失败定位，不替代修订测试的正控/负控结果。

`build/k4-cancel-dma-r4` 在用户执行取消后进入原 block deadline，panic 73。`build/k4-irq-diagnosis-r1` 对同一冻结产物用新盘和 QEMU interrupt trace 复现；不能凭系统累计出现过一次 U external IRQ 证明指定的那次 DMA 已走该路径。

`build/k4-irq-diagnosis-r2` 消费作者提供的源码诊断快照：仅增加 mask/release/unmask/U IRQ/consume 文本并重建 ELF、启动描述及 boot。日志顺序是 U IRQ → mask → release → unmask → enable读回正确 → deadline；唯一的 U IRQ 在目标完成前，故测试的计数断言没有误放行。

`build/k4-irq-diagnosis-r3` 用 QMP 只读观察停机后的设备状态：virtio interrupt status=1，PLIC pending=0x100、S enable=0x100、threshold=0，而 sip=0。它表明完成已发生，却没有送达 CPU；不是把没有完成的 DMA 强行标作完成。观测没有读取会消费中断的 claim 寄存器。

与[QEMU 的 SiFive PLIC 实现](https://github.com/qemu/qemu/blob/master/hw/intc/sifive_plic.c)对照：enable 写分支只更新 enable 数组；threshold 写分支调用中断线重算。这与本机 QEMU 11.1.1 的观测一致，但远端 master 不被冒称为本机二进制的精确源码身份。生产 hub 初始化已有 threshold 写入；触发条件是测试自行禁用/恢复 enable 且刻意停止 claim。

处理方向：测试保留 enable=0 屏蔽，恢复 enable 后额外写入原 threshold=0 促使模型重算，保留真实设备完成、真实 U trap 与生产超时负控，不改生产为测试制造完成，也不删除失败证据。类别是设备模型行为与测试控制的相互作用，修订后结果另记。
