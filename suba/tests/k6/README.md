# K6 验证

```sh
python3 tools/check_k6.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/k6-check
```

`--out` 必须不存在。工具冻结源码/资产副本并用同一 S-next ELF 编译正式实现，在 qemu-riscv64 执行。原始命令、产物身份、逐项期望/结果哈希和机器码栈审计保存在输出目录，不将大量逐例结果复制进设计文档。

- UTF-8：256种单字节、1–4字节边界、截断/续字节/overlong/surrogate/上界、10000个固定种子随机scalar；与 Python 严格 UTF-8 比较值和字节位置，同时检查边界/previous。
- 编辑：Python Unicode 字符串模型（不是另一份 gap buffer）核对每步内容、cursor、anchor、version；24组各100步混合移动/选择/插入/删除；另有中文、组合字符、四字节缺字、非法输入、小容量和精确4MiB边界。snapshot输出就是保存字节 oracle。
- 资源：失败open不损伤旧文档、copy容量不足不写输出、输入self-alias与rehome self-alias、反向选择、gap两侧decode、失败rehome、成功rehome后覆盖旧存储仍可完整读回新文档；字体转换失败不写输出。
- 字体：原生fontpack两次转换全量官方源，和独立Python wire oracle逐字节比较；正式 `.fnt` 必须完全相同。字形通过生产 `glyph/pixel` 输出并对照源hex像素，包括中/文、汉字边界、ASCII、四字节缺字。错误font header/width/surrogate拒绝。
- 负控：测试副本去掉overlong检查，必须正常解码出预期错误值；容量失败时故意破坏anchor，必须正常输出预期受损状态。单独把版本最大值缩为2验证耗尽不回绕且删除失败不破坏选择。这些故障副本不进入生产。

`cost.py` 对本次冻结后端生成的实际 RISC-V 前导解码每函数frame，并按模块解析直接调用图。未知前导、数量不符或递归会拒绝审计。Linux测试transport、固定测试缓冲和fontpack运行适配单列，不能用测试ELF的BSS冒充编辑核心需求。

本阶段不包含 suba 上的窗口/文件保存/编译集成；该证明属于 K7。测试运行在真实原生编译的 RISC-V 代码上，不以 Python 模型替代产品执行。
