# K4 存储故障探针

`python3 tools/check_k4_faults.py --kernel-from build/k4-filesystem-r3 --out build/k4-faults-r1`

输入是 `check_k4.py --case filesystem` 已成功构建及运行的冻结快照。每例重新格式化初始盘，保持同一个启动 ELF、内核 ELF 和用户测试 ELF；宿主只准备磁盘并观察串口，运行期没有文件服务。正常控制例必须先成功。

真实坏盘覆盖 superblock CRC、重算 CRC 后仍不合法的布局、节点 UTF-8、FAT 环；设备错误使用 QEMU blkdebug EIO，分别命中挂载读、启动代数写、FLUSH、运行期数据写、元数据写和数据读。后者要求先出现 mounted 标记，再出现明确 kernel panic；QEMU 命令失败和宿主超时都不能单独构成通过。panic 后内核停在 halt，测试超时负责关闭虚拟机。

依据：[QEMU blkdebug 文档](https://www.qemu.org/docs/master/devel/testing/blkdebug.html)。每例保留实际命令、配置、初始布局、串口日志及摘要。注入错误是预期故障，不属于实现 BUG；此测试也不声称验证突然断电恢复。

加 `--compiler ../biomiya/build/source-cap64-p4-r3/e3.elf` 会另外从同一冻结源码构建缺失完成通知的探针：挂载后屏蔽 block PLIC，实际数据请求仍提交，原 block deadline 到期后必须 panic 73。`build/k4-faults-r2` 已完成全部12例。测试快照改动与编译输入由报告保留。

专门验证用户 FileRead：`python3 tools/check_k4_read_fault.py --kernel-from build/k4-filesystem-r3 --compiler ../biomiya/build/source-cap64-p4-r3/e3.elf --out build/k4-file-read-fault-r1`。只读夹具在故障前没有写操作，排除 partial write 的内部 edge read 提前命中注入；旧矩阵的 `data_read_eio` 只按运行期驱动读错误解释。
