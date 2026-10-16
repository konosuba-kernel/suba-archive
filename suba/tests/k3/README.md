# K3 真实 U 模式回归

全部命令从 `suba/` 执行。固定 E3：`../biomiya/build/layout-p4-r1/e3.elf`，SHA `049c6e094ccd044fba3b5d357583013b77f0e8e9a98d431ad919e02b0cda2144`。需要 qemu-riscv64、qemu-system-riscv64 与已安装 OpenSBI。每次输出目录必须不存在；脚本保留输入快照、编译输出、最终 QEMU 命令、serial.log 和 verification.json。

```sh
python3 tools/check_k3.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/my-k3-spawn --case spawn
```

| case | 检查 |
|---|---|
| smoke | 实际 ecall、Unsupported、页/流基本生命周期 |
| memory | 128轮复用、精确free、513页跨叶表、零页与完整页基线 |
| streams | 64KiB满环、partial、背压、EOF/BrokenStream、错端权限、坏范围不消费、有效跨页 |
| spawn | 同一loader加载孩子，argv/cwd继承，显式writer继承，128KiB完整流与退出收集 |
| tree / orphan_tree | 父子孙；JobEnd或直接父退出，子树和全部引用清零 |
| waits | 16watch、全量验证、截止、kill/重复kill、stale Child、后继身份 |
| handles | 64句柄上限、第二端插入失败回滚、stale拒绝 |
| rollback | 真实96MiB配额触发多页失败回滚（不缩小生产容量） |
| blocked_writer | 满环阻塞写者kill、迟到写入拒绝、EOF及引用回收 |
| process_limit | 16个进程含根的容量、保留退出记录后创建失败回滚、槽复用 |
| spawn_invalid | 参数保留字节、路径、错端继承、部分writer继承后失败回滚 |

定点注入只修改明确标记测试副本，仍调用生产所有者，不使用替代allocator或另一套生命周期实现：

```sh
python3 tools/check_k3.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/my-k3-fail1 --case allocation_failure --mutation allocation-1
python3 tools/check_k3.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/my-k3-late --case blocked_writer --mutation late-token
python3 tools/check_k3.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/my-k3-reserve --case cancel_prepare --mutation cancel-reservation
python3 tools/check_k3.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/my-k3-install --case cancel_prepare --mutation cancel-install
```

allocation-0/1/2 区分没有页、只有新页表、有首数据页后的失败。cancel-reservation 杀死持未绑定退出记录的父；cancel-install 杀死已绑定孩子但尚未安装Child句柄的父。二者都要求最终所有资源基线恢复。

负控：`memory --mutation omit-prune` 必须得到用户断言退出15；`waits --mutation omit-token-revocation` 必须准确panic23；`streams --mutation prefix-only-usercopy` 必须准确panic22。脚本要求对应结果，不能将任意失败视为发现缺陷。

默认 `passed` 表示功能断言/预期负控成立，**不表示性能目标通过**。timing 单列5ms dispatch目标和测量结果；加 `--require-slice-target` 才将该指标作为命令失败条件。该指标不等于整个连续S驻留，也不覆盖未来真实IRQ与双编译任务交互延迟。时延比较应单独运行并记录宿主条件；不得只选择较好的一次结果。

正式入口常驻，不因Blocked或无进程退出；脚本仅在测试副本加入quiescent/free基线终点。原始内核ELF与高RAM权限来源仍是同一字节文件，无宿主重打包/patch。K2工具现在适配此常驻入口；历史K2冻结报告没有重写。
