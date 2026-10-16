# suba 内的构建工具

`/sys/build.elf` 是普通 U 态程序，编辑器通过 Child 和 Stream 调用它。它执行
`build MANIFEST [BLOCKING_POLICY]`，源路径相对调用者的 `/work` cwd；生产编辑器默认使用
`/work/program.build`，Ctrl+M 可选择其他清单，包括初始盘中的 `compiler.build`、`kernel.build`。清单采用当前 S-next 格式，目标为 `suba-user` 或 `suba-kernel`。
核心编译器不复制：suba 版只用 `runtime/host_suba.vt` 替换 Linux 环境适配。

一次构建依次经过：创建 Job、复制源文件和清单、记录 SHA-256、核对工作区 epoch 并冻结、
启动编译器、排空诊断并收集退出、校验完整 ELF、发布到清单 output 路径、结束 Job。
`manifest.vt` 只规划路径和边界；语言语法与清单规则仍由编译器判断。

编译器只读该 Job 的 src，写该 Job 的 out；不能写 `/work`，也不能通过派生子进程逃逸。
快照期间其他进程修改工作区会使 freeze 返回 Busy，本次构建失败，读者保存后重新构建即可。
冻结后的修改不影响已经启动的编译。

发布用独占 Transient 文件、写完、sync、close、原子 replace、sync_all。replace 是提交点：
此前取消或失败保留旧产物，此后取消不撤销已发布文件。损坏 ELF 和非零编译退出均不能发布。
输出的父目录可被建立；失败可能保留空目录。目录创建不等同产物发布。

`/work/.suba-records/<32 hex>/<32 hex>` 保存内容寻址构建记录：原清单、重写清单、每个
输入和编译器的哈希、boot/epoch、最终产物哈希。记录在产物前持久保存，因此取消可能留下
一份完整构建记录但没有发布产物；不能用记录存在判断发布成功。旧记录不自动清理，磁盘满
会明确失败。这里不承诺突然断电时的多文件事务恢复。

诊断流中的 `input N HASH PATH` 让编辑器将文件号映射回原路径。VT 文件先编号，S0 后编号，
与编译器一致。文件号 0 表示清单、策略等元数据，不作源码跳转。编辑器跳转前重新核对当前
内容哈希；旧偏移不会静默应用到不同源码。

路径受编译器和 FS 的共同边界约束：清单≤16 KiB，64 个 VT、8 个 S0，VT 总量≤4 MiB、
S0 总量≤1 MiB，快照源路径≤92 UTF-8 字节、13 个组件，每组件≤63字节。output≤96字节，
不能覆盖输入、清单、策略或 `.suba-*` 保留组件。没有 Linux 兼容层、宿主文件服务或动态链接。
