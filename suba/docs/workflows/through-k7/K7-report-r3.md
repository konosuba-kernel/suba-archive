# K7-r3：块设备通知与最终组合验证

候选为 K7-candidate-r3.json，正式内核 SHA256
`737f4cf3c24aa4cc85753694b3e7a00de595bf74bfbfb0a9a291fce07ea6c650`。
本轮修复 Virtio 空通知/陈旧通知被当作致命错误的问题：Idle、Submitted、Completed
均允许没有新 used 项的通知，保留状态、完成数和原始 deadline；坏 used head/length/status
仍拒绝。设备 watchdog 仍为原来的 10000000 ticks。新增首次失败诊断，安全映射只读 PLIC pending。

有区分力证据包括九组旧坏→新好通知案例、真实 FLUSH 延迟/超时及 EIO、两份原始失败输入盘
各三次启动与文件/分配账本核对、100 轮真实 DMA 取消回收。关闭用户外部中断的负控在首轮
按原 deadline 失败：设备已完成但通知无法服务，不能靠轮询绕过 IRQ 合同。

最终生产内核完成 GTK/XTest 全闭环：中文文本、编辑编译返回41/42、诊断失效、取消、保存和
同盘重启后返回42；完整 GUI 的报告位于 build/k7-desktop-r3/verification.json。
独立验收见 K7-acceptance-r3.md/json，完整证据身份见 K7-evidence-r3.json。

历史单次 panic70 与旧 job_dma 第61轮失败原因仍未知，原报告不改写；本次通过证明当前候选
修复确证协议缺陷且满足 K7 功能合同，不构成对历史事件的因果追认。任何新的无注入正常 panic
须重新开启阻塞。桌面交互和构建仍为秒级，性能测量与优化属于 K10；正常关机尚未接入生产。
