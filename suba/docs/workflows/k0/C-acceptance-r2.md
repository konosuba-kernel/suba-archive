# C-r2 独立验收：Accepted

验收者 `/root/k0_acceptance`，未参与实施。接受对象仅 C-r2；不接受尚未冻结的 P/S/H/I 或整套 K0。

逐字对比 r1 保存副本与当前 ABI README，唯一变化明确 kernel 使用 `[base,end)`，end 为排他结束地址而非长度；与 `BOOT_INFO_KERNEL_BASE/END` 及实际序列化字节一致。r1 唯一阻断已消除。

独立核验 C-r2 六文件哈希全部一致；除 README 外五文件与 r1 完全相同；r1 README 副本匹配原冻结哈希；原作者验证记录、独立三命令探针记录及规约/合同输入均未变。因此复用 r1 的真实编译/正向运行/错 sepc 负控证据，不重复执行未变程序，也不将本轮核对计作新的运行测试。

精确候选、文件与证据哈希见 [r2 evidence](C-acceptance-r2-evidence.json)；布局、编号、平台核验和边界说明继承 [r1 独立验收](C-acceptance-r1.md)。r1 的 Rejected 历史保留。

范围仍是常量、格式布局和保留编号；完整系统调用记录/服务、格式 decoder、CRC/UTF-8/链归属拒绝验证、suba 原生自举和磁盘重启均不由此次结论证明。下一步真实消费者必须使用该权威常量并补充实际边界验收。
