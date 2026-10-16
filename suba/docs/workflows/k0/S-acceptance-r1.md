# S-r1 独立验收

2026-10-14，验收者/root。**Accepted**，候选S-r1-candidate.json的11文件哈希全部匹配。

审查新增unsigned_field在乘法前以(maximum-digit)/base检查，负号/空hex/超12位CSR/超5位zimm拒绝；没有signed12掩码漏洞。独立核对system编码、S-type sh、仅全屏障fence、sfence.vma双寄存器和4..4096的2幂align；填充最多1023个32bit NOP且参与原有符号修补。没有改变外部ABI或新增可变状态。

独立执行 `python3 -O core-s/tools/check_q_s0_system.py --compiler core-s/build/k0-s-r1/compiler.elf --record-dir core-s/build/k0-s0-root-r1`：167/167通过，详见S-root-r1.json。查看Clang oracle的norelax/norvc设置及ELF .text读取，未用Q自己的编码公式当oracle；新增/旧指令80条完整字节比较、5个对齐、160反例、1个真实运行场景。查验作者旧E3负控不能通过新工具。Clang仅测试设施，不产生正式ELF。

这证明编码/解析和可在U-mode执行的sh/fence，不证明完整trap或中断回收；后续I以同一组合E3在QEMU执行特权机器路径。没有机械重跑完整bootstrap作为本组件独立验收替代物。
