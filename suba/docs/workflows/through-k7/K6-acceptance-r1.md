# K6-r1 独立验收：通过

2026-10-15，验收者 `/root`，作者 `/root/ram_fdt`。候选身份和复现日志 SHA256 见同名 JSON；32 个冻结文件逐一匹配。前置 K0 / suba `7712dd3` 未变。

独立阅读 UTF-8、gap buffer、移动/删除、字体验证与转换实现，检查失败检查先于写入、选择端点不跨 scalar、Document/Font 的借用生命责任及单所有者约束。没有生产全局可变编辑状态；4MiB 上界在 open/replace/rehome 保持。复制型语言的别名责任已明确，不冒充静态借用保证。

重新运行 `python3 tools/check_k6.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/k6-root-review`：348 项全部通过。另运行 `python3 docs/workflows/through-k7/K6-independent-r1.py build/k6-root-review`：4 项人工逐帧预期通过，覆盖零容量失败不变、满容量零 gap 上反向选择替换、四字节/NUL/汉字/LF 在 gap 两边删除、合法前缀后越界 scalar 的错误偏移。该独立脚本不调用作者的 Python Model。最初误将 UTF-8 探针视为流式输出；阅读其全量 validate 协议后修正测试预期，生产代码未改变。

完整字体经原生转换与逐字节 oracle 比对；查看实际生产 pixel 输出预览，中文与缺字方框正确。许可及源/产物身份已随资源记录；643 行手写 VT/S0 与独立字体数据的统计口径明确。机器码 frame 统计与最大调用链预算已重新生成。

本判定覆盖可移植文本/编辑/字体核心，不覆盖尚未实现的 suba 窗口与文件保存。K7 必须验证真实图形、保存、诊断版本关联和构建闭环；本节点没有放宽这些依赖要求。
