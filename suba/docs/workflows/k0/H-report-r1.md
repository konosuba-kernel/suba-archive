# K0-H：编译器运行环境边界（候选 r1）

基线 biomiya `a86586e`，规约 `CODE_STYLE.md` 0.1。只实现 Linux host 与可替换边界；suba 的真实文件/参数服务依赖 K3，此处没有伪装成功的 suba stub，也不宣称编译器已在 suba 内运行。

## 实现与接入

新增 `biomiya/core-s/next/q/runtime/host_linux.vt`，提供 `runtime::host`。构建清单明确选一份同模块实现，目标 profile 不参与 host 选择。它复用现有 `runtime::linux`，后者完全未改；没有第二套 Linux 文件实现、通用插件、句柄表或条件编译。

| 操作 | 合同 |
|---|---|
| argc / argument | 包含 argv[0]；参数只读，进程生命周期有效；最长 96 字节 |
| unsafe read_file | 同步、可能等待；调用者维持路径/缓冲有效且独占可写缓冲；必须有一个用于发现超长的额外字节；失败可以修改缓冲 |
| unsafe save_new | 同步独占创建；现有文件不覆盖；调用者拥有路径且禁止并发替换；完成包含权限终结与关闭，但没有持久化/发布承诺 |
| unsafe diagnostic | 同步 best-effort；可能等待、部分写入；有意丢弃诊断输出失败，避免覆盖原始错误/退出状态 |
| exit | 终止当前进程；即便异常地从底层退出调用返回也不返回语义层 |

host 只暴露 BytesResult、CountResult、SaveResult 和保存失败信息，未暴露 Linux fd、syscall 号或 WriteResult。save 错误保留 `errno/close_errno/cleanup_errno`，这些是后端局部的诊断数值，不供语义层解释。`phase` 是后端拥有的静态只读操作名，保存失败返回后仍有效；Linux 精确保留 create/write/chmod/close。未来 suba 可以给出自身真实的 seal 等阶段，不能假称执行了 chmod。

`model` 移除直接 syscall 声明、write 循环及 exit 调用，统一走 host。`blocking` 的策略文件读取与输出也只依赖 host。main/input 接入属于 P：import host，argc/argument/read_file/save_new 切换为 host，输出直接调用 diagnostic，保存阶段直接打印 `failure.phase`。compiler.build 和已有测试清单由 root 统一接入。

## 有区分力的验证

- `H-probe-r1.json`：3 个实际编译/执行场景。把真实 model 链接到测试 host，不包含 runtime/linux.vt：捕获精确 `E_TYPE file=7 byte=19` 并退出 77；吞掉所有诊断仍验证原始失败状态并退出 79；换回基线 model 的负对照触发禁止的旧 syscall 路径并退出 85。不是仅检查 import 字符串。
- `H-probe-optimized-r1.json`：同三例在 Python `-O` 下通过；工具使用显式 require，不依赖 assert。
- `H-io-r1.json`：12 个现有保存/路径场景全部通过，包括 NUL、已有文件、短写、write/chmod/close 失败及清理失败组合；精确核对原有诊断和残留权限。冻结 E3 编译真实 H + 隔离接入后的 input，而非运行旧 input 二进制。
- `H-build-r1.json`：由维护 E3 单次构建 H 隔离候选成功，SHA `3b37b59a89774f37bdcf339a1fd9cf2a755cc8f32d08b287ffdd7cfd49d5ae1a`，17 VT + 1 S0、names 4187、ELF 1,011,792 字节、max_frame 25,808 字节。它不是 P/S/H 组合，也不计为完整自举固定点。
- `H-diagnostics-r1.json`：18 个现有诊断场景与实际 IR 所属位置探针使用上面的 H 候选，结果由该记录确认。

所有构建/运行命令、返回值和哈希在相应 JSON。可重跑的 capsule 在 `biomiya/core-s/build/k0-h-r1/`（忽略目录），完整源输入哈希在 `H-source-inputs-r1.json`。隔离快照从基线读取生产源，覆盖 H 的三个生产文件，并仅在快照内接 main/input、host 清单和两个测试工具的模块列表；不依赖 P/S 正在修改的文件。

最初测试 fixture 的 S0 指令缺逗号，编译正常拒绝；修正为当前正式语法后重跑通过。原失败保留于 `H-probe-failed-initial.json`，不计通过。

## 成本与边界

生产净增 66 行：host 85 行，model/blocking 合计净减 19 行。专属验证工具和三份 fixture 合计 152 行。没有改 Linux 运行库的公开行为、语言语义、容量或冻结种子。

该测试替代 host 只实现 model 实际依赖的诊断/退出子接口，用于证明边界；它不是可用编译器运行环境。完整组合的自举、Blocking 和全部既有回归由 I 验证，独立验收由 root 判定；作者不自验收。
