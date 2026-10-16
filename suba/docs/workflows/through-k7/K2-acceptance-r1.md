# K2-r1 独立验收：通过

2026-10-15，验收者 `/root`，作者 `/root/memory_resume`。冻结候选24个owned文件、全部前置输入和21组作者原始记录身份均核对；精确身份见同名JSON。K2b已验收分配器保持原实现。

阅读页表映射/页归属、ELF解析/增量装载、进程状态与完整S0 trap/restore路径：内核U位不开放，用户RX/R/RW+NX分离，BSS清零，固件和栈guard缺页；sscratch在U持frame、在S为0；先保存用户寄存器再使用scratch，恢复状态不从用户信任SPP/SUM。ASID0每次activate执行sfence。页归属仅space持有，失败装载和退出走同一个有界reap。

预审指出的ELF总长/BSS offset溢出与未知高位中断分类已由作者在冻结前修正。启动器对原kernel ELF源负责，BootInfo与单独RAM描述符边界和保留登记已明确；没有把恶意启动器作为当前安全承诺。

独立重新编译并实际运行 basic、registers、rollback、privileged、s-guard、restore-negative，全部得到指定结果；37项ELF解析重跑通过。生产kernel ELF与作者冻结文件逐字节一致（352272 B）。每次测试在独立build目录保留输入快照和实际命令。作者其余故障场景日志身份已复核，源码中的对应权限检查也已审查。

追加 `K2-independent-r1.py`：生成额外的普通用户程序向0x3fe00000启动参数页写字节。真实硬件cause15只终止该进程，另一进程正常退出，全部用户页/页表回到基线。该反例使用冻结生产kernel，改变的只有用户fixture；不是生产路径注入成功标记。

`K2-stack-r1.py`检查实际ELF107个VT函数的机器码frame与模块解析直接调用图：最大单帧9344 B，start可达VT链24944 B，dispatch链5584 B，panic链1024 B。机器桥另占少量固定帧，S0包装不使用栈；当前没有递归，128KiB预算有足够余量。这是当前代码的保守直接调用链账，不是K7延迟或未来模块的栈证明。静态BSS6448864 B，Owned实际12 B，4.5MiB页账本完整计入，不用移动文件隐藏成本。

通过范围为完整K2。K3仍须提供动态unmap/槽复用、常驻idle、句柄/Request与外部资源回收门槛；K4/K5/K7没有被本判定提前验收。旧单阶段入口脚本不再是当前启动命令，替代回归入口及原因已记录。
