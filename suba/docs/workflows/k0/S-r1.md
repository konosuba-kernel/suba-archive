# K0-S r1：有界 S0 机器指令

作者为 `k0_machine`；状态为候选，独立接受由 root 记录。本节点不宣称特权指令已在内核执行；正式 S-mode 路径由 I 验证。

## 实现与明确语法

唯一生产修改是 `biomiya/core-s/next/q/s0.vt`，增加 91 行。保留既有指令与重定位路径，不改变 image/rv64 模块。

| 语法 | 边界与编码 |
|---|---|
| `sh xS, offset(xB)` | S-format，funct3=1；offset 为既有 signed12（−2048..2047） |
| `csrrw xD, csr, xS` | SYSTEM，funct3=1 |
| `csrrs xD, csr, xS` | SYSTEM，funct3=2 |
| `csrrc xD, csr, xS` | SYSTEM，funct3=3 |
| `csrrwi xD, csr, zimm` | SYSTEM，funct3=5 |
| `csrrsi xD, csr, zimm` | SYSTEM，funct3=6 |
| `csrrci xD, csr, zimm` | SYSTEM，funct3=7 |
| `sfence.vma xAddress, xAsid` | `0x12000073 \| (rs2<<20) \| (rs1<<15)`；两个寄存器必须显式提供 |
| `sret` | `0x10200073`；无操作数 |
| `wfi` | `0x10500073`；无操作数 |
| `fence` | `0x0ff0000f`；唯一形式为无操作数的完整 iorw,iorw 屏障 |
| `fence.i` | `0x0000100f`；无操作数 |
| `align N` | 字节对齐，N 为 4..4096 的 2 的幂；用 32-bit NOP `0x00000013` 填充 |

寄存器仍只使用 x0..x31。csr 是 unsigned12（0..4095），zimm 是 unsigned5（0..31）；十进制或小写 `0x` 十六进制。新增 `unsigned_field` 在乘法前检查范围，不经过 signed12 转换或掩码；负号、空十六进制、符号 CSR 名、非法寄存器和额外操作数拒绝。不增加 CSR 伪指令、fence 掩码语法、GNU 指令别名或任意 section/data directive。

align 的循环最多写 1023 条 NOP；依赖全部受支持 profile 的 text VA 为 4096 对齐。对齐后定义的符号取实际位置，原有修补路径因此自然看到填充。普通 U-mode 执行测试跨 4096 对齐标签跳转检验这条路径。

新增逻辑分为 unsigned 字段解析与有限机器指令分派两个辅助函数，没有公开新接口或引入新的可变全局状态。s0.vt 总长 521 行，超过规约的文件长度审查信号；保留同一有界汇编所有者与集中分派，不为此拆成多模块。

## 独立编码与操作数验证

`core-s/tools/check_q_s0_system.py` 的检查全部是显式 require，在 Python 优化模式下仍有效。固定 fixture 名为 `next/q/tests/k0-s0-*`。Clang 仅为测试 oracle，不进入 Q 的产物流水线。

环境中的 `riscv64-unknown-linux-musl-as/objcopy` 解析符号链接后实测为 0-byte 空文件，不能执行。按 root 指示使用本机 Clang 23.1.1 的 RISC-V integrated assembler：`--target=riscv64 -march=rv64im_zicsr_zifencei -mabi=lp64`；显式 `.option norvc` 和 `.option norelax`。验证器读取 ELF 的 `.text`，拒绝未决 text relocation，独立比较 Q 与 Clang 的完整标记区域字节，而非复制 Q 编码公式。

167 项包括：80 条新旧指令的全字节对照 1 项；4/8/16/256/4096 对齐及 NOP 填充全字节对照 5 项；非法操作数与超限数字 160 项；真实编译执行 sh、fence、fence.i、跨对齐标签跳转 1 项。csr 2048/4095、zimm 31、register 31、sh −2048/2047 等正边界与相邻负边界均覆盖。运行程序将 291 写入独占栈槽的第 2 字节偏移，通过 lwu/右移检查半字存储，并保留 x27、恢复 sp。

首次探索编译误从仓库根请求 `compiler.build` 得到 E_IO，未计入通过；之后固定在隔离源快照根构建。早期预检在更正 oracle 名称的注释前编译，最终候选另建，最终结果只引用精确冻结输入。未修改冻结种子与正式 compiler.build；隔离快照使用已提交 HEAD，唯独覆盖 s0.vt，避免其他节点未完成代码混入。

## 证据与边界

精确冻结源构建成功，编译器 SHA256 为 `3f29c54ea59f5fa27ef250fa5cf584d9989b1b843130bb24340da542afb11c8f`。最终验证 **167/167 通过**；同一验证器在 Python `-O` 下对旧 E3 返回预期失败（仅 3/167 通过）。

完整命令、哈希及通过情况见 [S-r1-results.json](S-r1-results.json)；冻结文件清单见 [S-r1-candidate.json](S-r1-candidate.json)。可再现命令（从 biomiya/core-s）：

```sh
python3 tools/check_q_s0_system.py --compiler build/k0-s-r1/compiler.elf --record-dir build/k0-s-root-check
```

产物位于 ignored build 目录；持久记录在本工作流目录。测试只证明汇编语法、机器编码、对齐、合法 U-mode 指令执行和拒绝边界；不证明 CSR 的权限政策、实际 trap 入口或内核生命周期。完整组合自举、既有回归与真实 QEMU 特权路径由 I 节点承担。
