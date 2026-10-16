# F-r1 独立验收：通过

验收者 `/root`，未参与 F 实施。候选 SHA256 `588e86b450a07ce648e3e6aec3f633333f24a661921098a98e2745d282eefdbf`；全部 15 个文件与 D-r3/ABI/编译器依赖哈希一致。

独立执行 `python3 tools/check_fdt.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/k2-ram-f-independent-r1`：359 合同场景、3 语义负控通过。输出冻结于 F-independent-r1.json。另自行构造 31 个合法 map 项后接越过 RAM 最后字节的 reserved reg，实际 Invalid 且不发布输出；恰好 RAM 最后一字节保留则输出原始范围，F-boundaries-r1.json 保留输入与实际结果。

逐行检查三个生产文件：read_header 建立各块单调有界关系；be32/be64/view 均在验证宽度后调用；树循环每次消费 token 且只用有界局部栈；语义仅识别根 memory、保留节点与 chosen 限制。map 内重叠拒绝，跨来源保留给 I 归并；属性先于子节点保证父 cells 在子 reg 前已确定。最末错误也不能发布局部 Description。reserved_name 比较借用仅在 inspect 生命周期内，无描述物理地址解引用。

核对成本：553 生产物理行，无可变全局；实测 inspect 最大 frame 8480 B、F 内调用链 19360 B。该节点不证明内核调用者栈总量或真实页池，需 I/A。非零 padding 只跳过已验证范围，不影响 token 位置。固定 v17/512 MiB 子集按合同明确拒绝其他内存语义。

无阻断。允许 I 正式消费 F-r1。
