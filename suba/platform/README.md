# 固定平台

首版 QEMU virt / RV64 / TCG / 单核 / 512 MiB / OpenSBI。设备与正式磁盘图形启动配置沿用 design/research/platform.md。K0 的串口探针不需要完整桌面设备集合；记录实际命令和固件哈希，不把该探针当作磁盘装载/桌面完成证据。

本目录 environment.json 固定本轮实际二进制身份。若升级环境，重新记录并重验受影响机器边界。外部QEMU/固件不属于本项目原生重建范围。
