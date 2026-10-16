# 规约示例

这些是 [CODE_STYLE.md](../../../CODE_STYLE.md) 的可编译教学示例，不是 suba 内核实现。

- `ranges.vt`：早返回、避免先加后验、私有字段维持构造不变量。
- `bytes.vt`：具体结果、普通RAM的unsafe合同、显式端序和范围验证。
- `main.vt`：正常/空区间/越界/溢出与短输入的行为检查；退出0为通过。

在本目录用当前S-next Linux-user编译器执行（编译器路径按实际工作区选择）：

```sh
qemu-riscv64 -s 1048576 /absolute/path/to/compiler.elf build program.build
qemu-riscv64 program.elf
```

编译器拒绝覆盖已有 `program.elf`；重跑请使用新的临时目录复制这四个输入文件，不要把旧产物误认为本轮输出。正式验证记录保存输入/编译器哈希、构建和执行结果；不会将生成ELF作为文档源文件提交。
