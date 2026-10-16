# FDT 组件合同测试

生产输入清单：`abi/contract.vt`、`platform/fdt.vt`、`platform/fdt_tree.vt`、`platform/fdt_properties.vt`。后三个文件共同组成 `platform::fdt`，导入只在第一个文件声明。测试通过 Linux 专用的 `probe.vt` / `linux.s0` 从标准输入读二进制 DTB，输出显式小端编码的 RAM / 保留范围；产品没有 Linux 或 dtc 依赖。

从 suba 根目录执行，`--out` 必须尚不存在：

```sh
python3 tools/check_fdt.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/fdt-check
```

`qemu-virt.dtb` 来自固定 `QEMU virt / 512M / smp1 / ramfb` 的 `dumpdtb`。`opensbi-runtime.dtb` 来自同一机器经过 OpenSBI 后，K0 引导代码已复制到永久引导区的真实 DTB；捕获命令和地址保存在 `runtime-capture.json`。原始资料位于 `build/k2-ram-explore/`，测试不依赖该 ignored 目录。运行时 fixture 的两段保留区域为 `[0x80000000,0x80040000)` 和 `[0x80040000,0x80060000)`。

`cases.py` 独立构造 wire 数据和明确期望；正例包含真实资料、跨来源重叠、非对齐、多 reg、no-map/reusable、精确容量。反例覆盖每一个最小有效树的截断前缀、块边界、溢出、畸形 token、重复内存属性/节点、嵌套/别名、动态保留、状态以及深度/节点/保留项上限。工具保存每份输入、每个执行结果、ELF 与编译器身份。有效资料另经 dtc 解码保存 DTS，不能将 dtc 当作产品解析器。

三项负控仅修改测试副本：漏掉 reserved-memory 的 reg、漏掉 reservation map、接受重复 memory。必须得到预期的错误 Ready/零保留区输出，不能用 crash、超时或任意非零退出冒充缺陷已被识别。

兼容性细节：实际 QEMU/libfdt 的属性 padding 包含非零旧字节；本实现验证 padding 范围和对齐而不解释内容。DTSpec 允许根节点前存在 NOP，而本机 dtc 拒绝这个位置；该规范正例不使用 dtc 作为准入条件。规范依据：[二进制格式](https://devicetree-specification.readthedocs.io/en/latest/chapter5-flattened-format.html)、[设备节点](https://devicetree-specification.readthedocs.io/en/latest/chapter3-devicenodes.html)、[属性命名](https://devicetree-specification.readthedocs.io/en/latest/chapter2-devicetree-basics.html)。属性名限定 31 字节，避免恶意 nameoff 反复扫描整个字符串块。

栈成本由工具按冻结编译器的机器码前导解码每个函数 frame，再与源中直接调用图组合；遇到不同前导/数量或递归会拒绝审计。这里只测 F 的 `inspect` 调用链，完整内核入口、I 的调用者与机器桥成本必须在集成节点另计。
