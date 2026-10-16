# K0-P r1：固定profile与有限机器桥

作者交付，等待root独立验收。精确合同见 [P-contract.md](P-contract.md)，候选文件身份见 [P-candidate-r1.json](P-candidate-r1.json)。不自认验收通过，也不表示K0已全部实现。

## 实现

- 新增69行 `target.vt`，统一四profile的基址/窗口/栈；image指令PC修补、静态指针与ELF段使用同一布局，高地址对齐改为相对偏移。
- 机器入口保留a0/a1、清SIE、不碰旧sp、清全部BSS、建立128KiB栈与x27=0；boot/kernel最低装载段首字节等于e_entry。
- 普通entry及两种bind有具体签名检查；`__suba_trap_dispatch`尾桥保留ra；机器panic/返回与用户退出分派至有限运行库终点。没有任意export或外部linker。
- main/input按H合同接runtime::host，诊断/保存语义未扩大。目标profile不决定编译器宿主后端。

四个已有生产文件净增148行，加target69行，合计217行；main仍238行、input440行。image601/rv641374行已有编码器规模，本轮不顺带重写其全部结构。程序入口和target分支以可独立命名动作表达，未新增框架或巨型context。当前临时编译器text1,027,200B、ELF1,036,432B、最大单函数frame25,808B；这是组合P/H/S源码的seed构建产物，不是P自身的独立增量成本，也不是调用链栈上界。

## 实际验证

运行目录 `biomiya/core-s`：

```
qemu-riscv64 -s 1048576 build/behavior-fixes-p4-r1/e3.elf build build/k0-p/compiler.build
python3 tools/check_q_profiles.py --compiler build/k0-p/compiler.elf --baseline build/behavior-fixes-p4-r1/e3.elf --record-dir build/k0-p/tests-r6
python3 -O tools/check_q_profiles.py --compiler build/k0-p/compiler.elf --baseline build/behavior-fixes-p4-r1/e3.elf --record-dir build/k0-p/tests-optimized-r1
python3 tools/check_q_profiles.py --compiler build/behavior-fixes-p4-r1/e3.elf --record-dir build/k0-p/old-control-r1
```

临时编译器SHA256：`df0e41d90e2d7d9edc04b20f8231181615af8f8a24c6b913ee5b0228e72f4fa4`。成功构建统计和清单见 [P-build-r1.json](P-build-r1.json)。构建从共享工作区加载源；记录源哈希是成功后核对，不代替I的构建前冻结快照和完整固定点证明。

[常规记录](P-tests-r1.json)与[-O记录](P-tests-optimized-r1.json)各26场景通过，使用显式require而非Python assert：

- 4profile ELF：3个PT_LOAD、RX/R/RW权限、地址/窗口/入口/文件边界检查；Linux样例运行退出37，并与冻结E3生成的整个ELF逐字节一致。
- 2个实际machine默认OpenSBI/QEMU virt启动；检查hart/DTB传参、栈对齐、x27=0、SIE=0、静态指针修补、kernel trap桥返回。
- 2个BSS污染后启动：`-device loader`在装载区填0xa5，实际入口仍把静态零对象恢复为0。不会把QEMU默认零RAM当作清BSS证明。
- checked越界panic进入绑定hook，reason101；普通启动返回进入hook，reason102。
- 17个拒绝场景覆盖未知profile/bind、用户bind、重复/缺失/错误签名、unsafe hook、boot trap、缺少halt/exit、重复桥符号及2MiB/64MiB窗口超限；拒绝后无输出ELF。
- 独立ELF读取器拒绝2个历史反例：最低PT_LOAD移至低地址、e_entry错离段首。

[旧编译器负对照](P-old-control-r1.json)按预期失败：冻结E3拒绝suba-user，工具未把它误记为通过。`git diff --check`通过。

开发中第一次临时构建因局部变量module用了保留词失败，改为module_name后成功。tests-r1至r5还分别暴露测试夹具extern/S0语法和诊断码期望错误，已修测试并保留ignored build中的失败记录；这些失败没有被计为通过。生产实现没有依赖宿主ELF修补通过测试。

## 边界

P不是完整kernel，也不是K1磁盘加载。kernel探针由固件直接进入，I仍需正式stage0→kernel流程。suba-user本工具仅检查生成/链接，test-only出口是无限循环，不能当作suba syscalls实现。I须提供真实运行库或明确记录未完成项。128KiB初始栈没有guard/独立panic栈，也没有整条调用链预算；trap现场保存/切栈/CSR恢复/隔离由K2实现。全部原有回归、自编译固定点与源码扰动仍由I针对冻结组合执行。
