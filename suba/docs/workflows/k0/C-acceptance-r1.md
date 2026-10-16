# C-r1 独立验收：Rejected

验收者 `/root/k0_acceptance`，未参与实施。判定对象仅 C-r1 六个冻结文件；不判定 P/S/H/I 或整个 K0。所有候选哈希、四个环境二进制哈希核对一致；精确输入哈希、真实子命令与 stdout/stderr 见 [evidence](C-acceptance-r1-evidence.json) 和 [checks](C-acceptance-r1-checks.json)。未修改受验代码。

## 唯一阻断

`abi/README.md:5` 将 BootInfo 的 kernel 两个 u64 写作“地址与长度”，但 `abi/contract.vt` 定义 offset48 为 `BOOT_INFO_KERNEL_BASE`、offset56 为 `BOOT_INFO_KERNEL_END`；实际 VT 与独立 Python oracle 在56写的是 `0x80440000`，即排他结束地址。若消费者按文字将其解释为长度，会接受/计算完全不同的内核跨度。必须统一为 `[kernel_base,kernel_end)`，明确 end 是排他地址，而非字节长度。数值、探针和已验收设计的“实际装载结束”一致，无需修改它们。修改后另冻结 C-r2；保留本次拒绝记录。

## 已通过的独立核验

从 suba 目录执行：

```sh
python3 tools/check_abi.py --compiler ../biomiya/core-s/build/behavior-fixes-p4-r1/e3.elf --out build/k0-acceptance-c-r1
```

实际执行编译、正向运行、错 sepc 字节运行三条 QEMU 命令；退出分别0、0、12。正向输出与独立常量字节 oracle 完全一致；负控不发布 actual.bin。编译器 SHA256 为 `8051f3599704a6bf180496b14632691c3463f1239946893641f65aae21969904`。核对测试记录输入哈希；工具使用显式失败判断，不受 assert 移除影响。

人工对照 CONTRACTS 检查七种记录的字段宽度/范围、保留区和编号。追加独立检查确认38个 syscall 号互不重复、15个状态互不重复；BootInfo reservation 表不越界，节点区/FAT容量、节点名范围、TrapFrame内容及对齐、RAM/image/boot相邻边界无冲突。六项 VT 几何检查实际通过。外部字节 oracle 不解析 contract.vt 或复用其常量，有区分力。环境实际文件哈希与清单一致。

## 范围及后续缺项

这是记录布局、编号保留与原生 S-next 常量构建验收。Syscall 号分配不证明调用服务已实现；完整参数记录和 decoder/usercopy 仍须后续节点冻结/验收。当前 byte probe 的 boot header/superblock CRC 为占位数据，未构造完整合法磁盘；它不能证明 CRC、UTF-8、reservation、FS链归属或恶意输入验证器。后续真实消费者须补足全部字段和拒绝边界，不能把七种样例字节等同完整语义覆盖。无 suba 内运行编译器、磁盘重启或桌面完成结论。

按 CODE_STYLE 检查，本节点纯常量无隐藏状态/宿主生成，unsafe仅测试内有界字节操作，长run为单个显式布局样例，未发现除上述文字冲突外的阻断。
