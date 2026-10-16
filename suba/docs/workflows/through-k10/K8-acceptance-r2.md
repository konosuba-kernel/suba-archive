# K8-r2 独立验收：通过

验收者 `/root/k4_review` 未参与 K8 实现。候选 `K8-candidate-r2.json` SHA256：`0428adb9b1a9f56337753d9f428da0728cbda5871507f69b37097dc7b09b3d69`。依赖 K7 提交 `08a4d07` 及已接受的 K7-r3；生产 kernel 为 `737f4cf3c24aa4cc85753694b3e7a00de595bf74bfbfb0a9a291fce07ea6c650`。

本候选满足 IMPLEMENTATION 的 K8 原生固定点、源码行为扰动、Linux/suba 同目标输出对照及子进程退出回收门槛，可以解除 K9 依赖。K9 和 K10 尚不在本报告的接受范围。

## 输入与实际执行链

独立核对 3 owned、7 helpers、81 实际编译输入、34 初始盘输入，全部匹配。实际 RAM 控制程序入口是 `test::native::main`，不是仅执行扰动的探索入口。初始盘只有 C0、源码和清单，不存在 C1/C2/C3/mutant 产物。C0 每个源码输入与正式 system 中 compiler 构建输入逐项相同，含 host_suba 和 syscall 汇编；内核复用检查源哈希和 ELF，未重写内核语义。

完整执行 `build/k8-native-r1` 由协调者启动，验收者审查控制程序、构建/运行命令、阶段记录、QMP 记录、最终磁盘和导出产物，而不声称亲自重新执行了整个长链。guest 普通进程实际执行：C0 编译 C1，C1 编译 C2，C2 编译 C3；guest 比较完整文件；C3 编译并执行 hello 得到41；原 C3 无参数退出2；guest 将 compiler/main.vt 首个 `return 2;` 的单字节2改为7，C3编译 mutant，执行 mutant 无参数退出7。

独立从磁盘读取验证 C0=C1=C2=C3 **完整 1,061,008 字节相等**，SHA256 均为 `872580a5751997a32c7b91c127987117e375a866fa99ecb36292ab443d0bb63c`。mutant 同样长但字节不同，SHA256 `6b21f25989ce1fa85b7832a54f56c9caeeeede76b4636d1dd40e04ad0fc4aa76`；源码恰好改变一字节。before/after 的文本 usage 相同，行为证据来自实际收集的退出码2/7，不能用日志文本相同误判扰动无效。

host 的 c1/hello/mutant oracle 在 guest 停止后生成，读取回传的扰动源码；三份 ELF 与 guest 产物全字节相等。这里比较的是同一 suba-user 目标，Linux 是运行宿主编译器的环境。QMP 记录只有 capabilities/screendump，运行命令无 host 文件服务，观察器没有向运行中的磁盘写入产物。

## 独立区分验证

`build/k8-independent-r1/` 为独立证据目录：

- `integrity.json`：冻结身份、K7 依赖、实际 main 入口、初始后代产物不存在。
- `products.py` / `products.json`：从停止后的真实磁盘读取全部代际、日志和源码；验证完整字节固定点、单字节源码扰动、实际阶段2→7及QMP范围。
- `run.py` / `controller.vt` / `verification.json`：创建新盘，从本次完整运行导出 C3/mutant；独立控制程序调用普通 U 进程，校验 C3 usage2、mutant usage7；让 C3 编译一个此前不存在的循环程序，运行结果73；退出后页回原基线、流和文件为0；独立 Linux-host 构建相同新程序，ELF全字节相等。实际新QEMU运行103.98s。
- `summary.json`：上述输入、脚本、产物与结果的 SHA；独立新程序 ELF 为 `4d71ecafcbfc1a12b4394305903926727c99d5e74d3c4091c083ad45c23de623`。

独立运行复用了已审查的管道/collect测试辅助函数和机器启动工具，未把这些称为独立实现的生产代码。它增加不同程序、不同预期结果及新盘，验证本次 C3 的可执行性和行为扰动，不只是重跑作者成功命令或重复哈希。

`finalize.py` 最终重新核对候选及正式 verification，三份宿主 oracle 全字节匹配。作者 compiled_inputs 额外含未直接编译的 tests/k0/boot.vt 模板；实际编译的是候选已锚定的 test_boot.vt，模板也独立核对无漂移。

原完整控制程序在每个固定点编译退出后检查页基线，最终检查页/streams/files/requests，所有 stats 必须为 OK；collect 要求正确退出码且 cause0。成功阶段只有这些断言及 sync_all 都完成才显示。K8 证明这条编译子进程链回收，不以它代替 K10 的各类百轮终止/全部资源压力矩阵。

## 修订与边界

r1 候选把 oracle/exported 派生产物误列入实际编译输入，oracle/main.vt 又会在 host 扰动对照中改变。本验收者在最终对照前指出；r1 原件保留，r2 改为按实际 manifest 精确列举81项。生产/测试源码和本次guest执行未改变，不需要为清单更正重跑1349秒的原生链；该更正不能追认r1清单始终无漂移。

完整guest约1349.04s；阶段观测累计时间 C1=310.05s、C2=632.80s、C3=974.64s，它们是启动后的累计时间，不是各轮单独耗时。本报告不把该结果称为实时响应达标。

K7 记录的旧 remount panic70 与旧 job DMA 单次 code100 仍保持未归因，本次运行未复现；没有借固定点成功声称解释历史故障。K8 产物来自当前 S-next、既有host种子构造初始盘和启动器；它证明 suba 内普通编译器自编译，不声称去掉所有引导种子，也不包括内核自身构建。

验收者未修改作者冻结文件，未提交。本报告冻结后可以按项目 DAG 进入 K9 正式实施与验收。
