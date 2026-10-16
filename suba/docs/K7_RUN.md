# 构建并运行工作环境

这是当前工作环境的使用入口。阶段验收结论和限制以
[推进至 K10](workflows/through-k10/DELIVERY.md)中的独立报告为准。

在 suba 仓库目录执行，明确指定已验收的 C64 编译器：

```sh
python3 tools/build_system.py \
  --compiler ../biomiya/build/source-cap64-p4-r3/e3.elf \
  --out build/my-system
python3 tools/run_system.py build/my-system
```

构建需要 qemu-riscv64；运行需要 qemu-system-riscv64 的 virt/ramfb/virtio 与 GTK，以及
`/usr/share/qemu/opensbi-riscv64-generic-fw_dynamic.bin`。固定单核、512 MiB RAM、256 MiB磁盘。
输出目录必须是新的；构建会保存源文件快照、编译命令、ELF及初始盘。`run_system.py` 使用已存在
的持久盘 `build/my-system/deployment/disk.raw`，**不会重新格式化**。
根目录的 `disk.raw` 是初始模板；实际运行和保存使用 deployment 内的副本。重复 build 不应覆盖你保存过源码的目录。

初始 `/sys` 放普通编译器、构建工具、编辑器和带许可的字体。只有可信desktop从RAM启动；
其余应用全部从guest文件系统加载。`/work/hello.vt`、`program.build`、`syscall.s0` 是可编辑
的首个项目；`notes.txt` 展示中文。`/work/system/` 保存构建所用系统/编译器源码。
Ctrl+M 可选择 `/work` 下的 `compiler.build` 或 `kernel.build`，然后 Ctrl+B 构建。
输出分别为 `/work/compiler.elf`、`/work/kernel.elf`；清单路径均相对 `/work`。
编译器固定点已完成 K8 验收；内核/S0 构建以 K9 报告为准。

[编辑器操作](../user/edit/INTERFACE.md)列出快捷键；[构建工具](../user/build/README.md)解释
冻结、取消、发布与构建记录。当前无电源管理UI；不能将直接关闭QEMU声称为已完成全系统正常
关机协议，更不能据此宣称突然断电恢复。先保存并等构建结束；测试中的停止与重启边界有单独记录。

## 当前检查入口

- `tools/check_k7_planner.py`：实际RV64规划器、路径边界、SHA-256互操作。
- `tools/check_k7_kernel.py`：真实FS映像、Job权限、发布/死亡、取消/迟到DMA与反例。
- `tools/check_k7_pipeline.py`：真实编译器与build的成功、错误、取消、坏ELF及回收。
- `tools/check_k7_desktop.py`：真实GTK输入，中文、修改源码、构建运行、诊断、取消和持久盘重启。
- `tools/check_k6.py`、`check_fs_metadata.py`等纯组件检查仍可直接验证对应生产组件。

各工具用 `--help` 查看必需输入。GTK自动化额外需要Xvfb和XTest，可指定 `--xvfb /path/to/Xvfb`；
它建立独立X11环境，不控制用户桌面。磁盘观察器只读已经停止的测试盘，不参与guest运行时服务。

K2–K5早期阶段运行探针与当时的启动/RAM应用夹具绑定。历史验收必须在对应提交或已冻结快照
复现，不能把旧脚本读取最新内核后的失败解释为旧验收失效，也不能把旧通过当新组合通过。
K7当前完整系统使用以上FS与受保护controller入口；没有为了兼容旧测试恢复 `/boot/N` 应用提供者。

## 原生内核的宿主部署边界

guest 在保存并同步完整内核 ELF 后，宿主从停止的磁盘只读导出该文件；固定 RAM boot 在
初始环境构建时生成，与之后的 kernel 无关。使用 `tools/ram_launch.py --help` 查看搬运参数，
传入 guest 输出的完整 SHA256、既有 `build/ram-boot.elf`、可信 desktop 和持久盘。
该工具只复制文件和写启动描述，拒绝错误身份、ELF范围、复制期间变化及再次启动前的改动。
以 `tools/run_system.py DEPLOYMENT` 启动搬运结果。不能用宿主重新编译的 kernel 替换guest输出
后仍声称原生构建验证；K9测试保留同输入host oracle，但它不进入部署。
