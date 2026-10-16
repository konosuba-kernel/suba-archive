# D-r1 独立合同验收

2026-10-15。判定：**通过**。作者 `/root`；独立验收者 `/root/ram_acceptance`，未参与合同编写或 F/M/I 实现。本判定只接受实施合同，不表示代码已实现或运行通过。

候选 `D-candidate-r1.json` 的 CONTRACT.md SHA256 为 `0529e9087e52bcb76fe0a5ee37d28586ff15e80665c5785ba0a9a56f93e188bc`；用 Python hashlib 与候选逐文件核对，无漂移。阅读 DELIVERY、CODE_STYLE、design/CONTRACTS、docs/K2_MEMORY、ABI 常量、现有页分配器及 K0 RAM 引导 fixture。

## 判定依据

- 地址来源与信任边界闭合：BootInfo 只能先在固定引导区内访问，复制 DTB 在永久保留窗口；F 只解码切片、不解引用物理描述；I 负责范围归一化；M 只接受调用者明确转交的页。可信 loader 报告 kernel_end 的限制已明确，不混称隔离恶意装载器。
- 保留区来源完整覆盖当前固定平台：固定固件、整个引导窗口、实际 kernel ELF 内存跨度、DTB reservation map、reserved-memory 与 BootInfo 项。原 DTB 只有复制结束且无引用后才能复用，FDT 保留不会因复制而释放。旧 BSS 页池不再重复捐出。
- 对 DTSpec 的固定子集取舍安全：v17/单根 memory/固定 cells/单 RAM 区/静态保留都是可显式拒绝的支持边界；未知设备不生成 RAM；动态保留和非空地址翻译不能静默跳过。对保留范围向外取整，不以读回禁止区域证明未使用。
- API 可组合：F 最多 32 项、BootInfo 最多 16 项、固定 3 项，共 51 个输入范围，归并后补集最多 52 段，64 段容量足够。M 通过 span 页号保持高偏移身份，在洞中不要求物理可访问性，旧单段入口可复用；失败先验证后发布与原生命周期一致。
- 初始工作有界且不全 RAM 清零；现有固定槽表与 128 KiB 栈属于成本验证责任。合同要求生产代码、测试、工具、ELF 和 frame 分别计量，不能以单帧最大值冒充调用链栈界限。
- DAG 独立性与范围明确：F/M 文件互斥、I 待两组件独立通过、最终 I/A 由未参与实现的 reviewer 验收；暂缓上一轮错误码/固定容量/文本注入评审项不导致本次安全边界缺口。

## 规范核查与非阻断提示

对照 [DTSpec 第 5 章](https://devicetree-specification.readthedocs.io/en/latest/chapter5-flattened-format.html) 的 reservation map 不重叠、零对终止、块对齐、单 END 与属性先于子节点要求，以及 [第 3 章](https://devicetree-specification.readthedocs.io/en/latest/chapter3-devicenodes.html) 的 reserved-memory 静态/动态与空 ranges 规则。合同是固定子集，拒绝通用规范允许的其他配置不构成违约。

后续验收特别检查真实 OpenSBI 运行时 DTB，不能只用 QEMU dumpdtb；边界算术、最后页清零、洞后页身份、拒绝后可重试、遗漏两类保留来源的反例必须实际可观察。完整调用链栈成本须包含 F 的按值 Description 与遍历状态复制。以上是已写入合同的实施验收重点，不是附加放行条件。

未发现阻断；可正式派发 F 与 M。I 尚未实现，仍需独立组合验收。
