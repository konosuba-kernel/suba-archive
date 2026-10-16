# H-r1 独立验收

2026-10-14，验收者/root，未编写H生产实现。判定 **Accepted**，范围仅H运行环境接口及其model/blocking接入；P main/input与完整组合另验。

核对H-candidate-r1.json全部15文件哈希一致。源码审查确认model的终止诊断不再发syscall、blocking只依赖host；host的六项操作不读target。Linux低层未改，不复制文件生命周期实现。静态phase文本、best-effort诊断和terminal exit的失败合同明确；pub unsafe的read/save/diagnostic存活责任在声明处。

独立执行 `python3 -O core-s/tools/check_q_host.py --compiler core-s/build/behavior-fixes-p4-r1/e3.elf --baseline-model core-s/build/k0-root/baseline-model.vt --record-dir core-s/build/k0-host-root-r1`，三例全通过：当前model由替代host捕获正确错误与状态、诊断被丢弃仍保持退出状态；从HEAD读取的旧model触发禁止的旧syscall负对照。构建命令/实际退出值/输入hash见H-root-probe-r1.json。不是仅查看import或比较相同生成代码。

审查作者隔离候选来源与IO12/诊断18记录，生产三文件匹配当前H候选；旧Linux错误/残留格式保留。未机械再跑完整组件回归，最终组合I将用同一新E3覆盖。没有suba文件服务实现、suba内运行或完整自举的通过声明；这些不属于H当前接口交付。
