# I-r1：实际 RAM 集成候选

作者 `/root`；独立验收者 `/root/ram_acceptance`。依赖 D-r3、F-r1、M-r2 及各自已通过的独立记录，冻结输入见 I-candidate-r1.json。未提交；没有修改 biomiya。

## 实现

启动现在为 machine 初始化 → BootInfo 纯解码 → FDT 纯解析 → 保留区取整/排序/归并/求补 → 唯一 memory 所有者一次性初始化。所有描述读完前不改页池；实际 kernel_end 仍是可信加载器前提。description 按值暂存，无外部借用留存。动态 FDT 语义明确拒绝。启动不清零全部空闲 RAM。

删除 kernel/bootstrap_memory.vt 专用 BSS 池，避免同一页有两个来源。旧 64 页集成脚本/探针删除并由 check_ram_boot 和 tests/k2_ram 替代；旧文档和冻结 K2a 记录保持历史字节，当前 README/K2_RAM 导航说明替代关系。check_kernel_entry 只更新源清单和异常注入位置，原四场景裁决条件不变。用户暂缓的三项评审建议均未处理。

## 作者实际验证

- `python3 tools/check_boot_info.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/k2-ram-info-r1`：543 场景通过，包括全部截断前缀、字段/保留字节、外部DTB/溢出/未覆盖拒绝和 16 项上界。
- `python3 tools/check_kernel_entry.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/k2-ram-k0-r1`：4 场景通过。正常启动、错误magic、可信异常、成功标记后异常必须拒绝，均真实 QEMU 执行。
- `python3 tools/check_ram_boot.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/k2-ram-i-r1`：6 场景通过。实际跨越 map/reserved-memory/BootInfo 三处非页对齐保留洞，取回整页为零、旧身份拒绝、free计数恢复。错误DTB/Info分别 panic4/1；漏FDT排除实际遇到禁止页 panic26；漏clear在脏页再分配时 panic24。
- 上游独立 F：359+3负控及2个root另构造边界；M：12场景。证据保存在对应节点文件，没有把组件执行冒充内核执行。

每轮生成两份独立 ELF；测试宿主独立解析 ELF 的三个 PT_LOAD，将真实 kernel_end 交给固定 RAM loader。内核探针先编译定尺寸再写容量常量，要求第二次生成的内存 end 完全相同，否则测试失败。三个洞共6页，其预期来自固定测试地址，不复用生产归一化逻辑。QEMU保留500ms成功后观察，不声称永久活性证明。

## 成本与边界

`tools/measure_kernel.py build/k2-ram-k0-r1/valid/build/kernel.elf` 解码当前后端所有函数前导，要求与源函数数一致。完整正式 kernel.build 包含 **1462 物理行 / 58446 B**，其中共享 ABI、平台和机器 S0 均计入；测试/工具独立分组，见 I-cost-r1.json。F/M详细成本沿用对应记录。

正式 ELF RX 153260 B、R 383 B、RW memory 1704016 B（含固定页元数据、128KiB栈及状态）。最大单函数 frame8480 B；全部 VT 函数 frame 求和为70352 B。源码无递归/间接调用，生产类型对齐不超过16；编译器 entry/copy/call/panic/trap桥和S0不额外下移sp，因此这是比任意实际调用链更宽的上界，仍小于131072 B。不是运行时栈水位测量。初始元数据有界扫描最多131072页槽，最多51原始范围，排序最多1275次；运行期allocate/release沿用M的O(1)元数据与单页清零。

当前仍裸S-mode、单hart、关闭中断，异常即停机。未实现页表/用户态/trap调度/隔离；不能声称普通进程崩溃可回收。FDT不是通用设备发现；宿主构建测试是本阶段验证，不是guest自举。README和K2_RAM给出下一阶段边界。
