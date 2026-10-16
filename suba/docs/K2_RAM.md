# K2b：接入实际 RAM

2026-10-15。固定 QEMU virt、RV64、单 hart、512 MiB。编译器为相邻 biomiya 的 `build/layout-p4-r1/e3.elf`，SHA256 `049c6e094ccd044fba3b5d357583013b77f0e8e9a98d431ad919e02b0cda2144`。本轮不改编译器，不增加语言或汇编指令。

## 启动路径

`kernel/entry.vt` 关闭中断并设置紧急异常向量，随后调用 `platform/boot_info.vt` 解码固定的 512 B 记录。记录本身和复制 DTB 均须完全位于永久引导窗口。只有检查 ABI、保留字段、计数、RAM 范围、内核边界、DTB 被登记区域完整覆盖后，才允许读取 DTB。

`platform/fdt*.vt` 作为一个纯解析模块，校验固定平台 v17 设备树并返回 RAM 与保留区。包括 reservation map 和 `/reserved-memory`；动态分配、地址翻译、usable-memory 等未支持的内存表达明确拒绝。其他设备节点只检查结构，不作运行期设备发现。

`kernel/ram.vt` 将最多 51 个原始保留项向外取整为页、排序、归并并求补集，最后一次性把最多 52 段 RAM 捐给 `kernel/memory.vt`。固件 `[0x80000000,0x80200000)`、引导 `[0x80200000,0x80400000)`、内核实际 ELF 内存范围始终排除。原有 BSS 64 页临时捐赠池已移除，只有一个分配器拥有可分配页。

初始化只写分配器元数据，不遍历清零约 500 MiB 可用 RAM；每次 allocate 才清零返回的一页。代数身份、重复释放拒绝和耗尽/退休语义沿用 K2a。Stats.capacity 统计实际捐赠页，索引边界使用整个物理跨度，二者不混用。

## 构建与验证

在 suba 根目录运行，每次使用新的输出目录：

```sh
python3 tools/check_boot_info.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/ram-info
python3 tools/check_fdt.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/ram-fdt
python3 tools/check_memory.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/ram-memory
python3 tools/check_kernel_entry.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/ram-k0
python3 tools/check_ram_boot.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/ram-qemu
```

前三项使用 Linux 测试传输环境执行实际生产模块，不代表内核上运行。后两项使用 Q 生成独立 boot/kernel ELF，QEMU + OpenSBI 执行真实 S-mode 代码；宿主不汇编或链接产品 ELF。dtc 仅构造/检查测试用 DTB。

`check_ram_boot` 覆盖正常分配回收、三个来源的非页对齐保留洞、错误 DTB、错误 BootInfo、故意遗漏 FDT 保留区和故意不清零。保留洞的页号为 `0x81001000..0x81003000`、`0x81202000..0x81205000`、`0x81403000..0x81404000`，测试实际持有穿过全部洞的分配，验证地址均不落入洞、释放后旧身份失效、再分配整页为零。测试不读取禁止区域。

原 K2a `tools/check_memory_boot.py` 和 64 页内核探针已由此组合测试替代，旧提交与 `docs/workflows/k2-memory/` 记录作为历史保留；旧命令不再是当前验证入口。K0 的四个成功/失败/成功后异常观察场景继续运行，仅跟随新入口更新注入位置。

## 边界与下一步

当前是裸 S-mode、串行初始化、可信加载器和驱动。实际 kernel_end 由宿主独立检查 ELF 后提供，不能抵御谎报加载范围的加载器；BootInfo CRC 字段只作为 ABI 元数据，不声称已校验镜像完整性。平台范围外的 DTB 指针会拒绝，但整个固定引导窗口可读仍是平台前提。

异常仍立即停机；没有 Sv39 页表、用户态、IRQ/抢占或应用故障隔离。下一步是在此页所有权基础上实现地址空间，再实现 trap 与进程生命周期。当前固定约 1.5 MiB 页元数据表仍在，按用户要求不在本轮优化。

具体源码身份、成本和验收证据见 [交付 DAG](workflows/k2-ram/DELIVERY.md)。全部能力仍属于完整系统的早期步骤，未完成系统内编译或桌面闭环。
