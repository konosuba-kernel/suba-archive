# 首版目标修订与 K2 内存起点

用户明确同意：首版必须原生构建应用、编译器固定点、内核及必要 S0；暂不要求系统内安装/切换内核，宿主可按字节搬运产物并用固定 RAM 启动链装载，不得重新编译/链接/修补。沿当前已接受 K0 I-r2 继续。旧验收冻结记录保留，当前设计修订需记录失效范围。

采用 dag-delivery；依赖 DAG：R → M → I → A。R 根据用户最新授权和现有架构修订目标；M 是本轮 K2a，I 在真实 QEMU 启动链验证。K2 其余页表/trap/抢占/进程机制继续保持未实现。

|节点|作者/写入范围|独立验收|验收条件|状态|
|---|---|---|---|---|
|R 目标修订|/root/scope_revision；REQUIREMENTS、README、CODE_STYLE的陈旧路径/状态说明、design/ARCHITECTURE/CONTRACTS/IMPLEMENTATION和新增范围修订说明；不改历史验收/ABI生产常量|root|首版构建与部署界限一致；K1磁盘更新移出关键路径，K4块设备所有权明确；保留正常持久化/隔离/原生固定点要求；旧记录不冒充新验收|R-r1已独立接受|
|M 物理页所有权|/root/physical_memory → /root/memory_resume；kernel/memory.vt、专属tests/memory及tools/check_memory.py、M-*候选/报告|root|仅分配可信调用者独占捐赠的页对齐整页RAM extent；不自行推断RAM空闲；具体页身份、重复/stale释放拒绝、分配失败受控、重新分配清零；操作推进上界清楚；无第二套生产分配器|M-r1已独立接受|
|I 启动接入|root；kernel/entry.vt/kernel.build、tests/k2、专属QEMU检查、当前阶段说明和I-*证据|/root/k2_acceptance|新E3直接编译，真实物理页读写/清零/回收通过；K0仍有效；记录成本/边界，不能声称有用户隔离|I-r1已独立接受|
|A 最终组合验收|/root/k2_acceptance；acceptance-*，ignored build探针|独立判定|核验最终源码/依赖身份，关键失败反例和实际QEMU证据；无未处理阻断|A-r1通过，无未处理阻断|

不自动提交本轮实现与用户的biomiya迁移。所有文件/候选按内容哈希冻结；返工增版，保留失败证据。当前规范仍为CODE_STYLE 0.1，R可纠正陈旧状态/路径但不得悄悄削弱规约。物理页实现必须明确初始化是引导期操作、运行时操作的上界和unsafe证明；暂不发明进程/权限模型替代后续K2/K3。

M在R等待期仅做只读接口探索。定案：initialize接收独占捐赠的[]u8，核验页对齐/整页/加法边界/容量；一次成功初始化不可重置。Frame私有index/generation，公开动作需串行、不重入、release前无映射/DMA/借用的unsafe证明；不是语言线性类型。O(1)free list，allocate最多清一页，代数耗尽退役。I使用kernel BSS内专属对齐arena，真实物理页读写；全RAM保留区解析与接管保持后续任务。

2026-10-15恢复：原会话子代理已不存在。R-r1文件哈希再次核对无漂移；M仅留下未冻结memory.vt/common.vt，由/root/memory_resume接续，保留原作者身份。最终验收者将重新绑定未参与实现的agent。

I等待M期间，root只在ignored `build/k2-integration-draft/`准备接入草稿（64页BSS捐赠与真实页测试），不计实现/验收成果。生产entry/清单未改；只有M独立接受后才正式接入和运行组合验证。


2026-10-15 最终交付：R-r1 → M-r1 → I-r1 均已接受，独立 A-r1 通过。当前生产入口/清单已正式接入捐赠页池，上述“等待期间未改”仅为历史状态。组件独立 8/8；真实 QEMU 页池 2/2、K0 4/4；额外 QEMU 漏清末字 panic 24、代数固定 panic 26，均拒绝成功事件。全部冻结源码/依赖身份在收尾再次核对，无漂移。

- [本轮实现与边界](../../K2_MEMORY.md)
- [R 独立判定](R-acceptance-r1.md)
- [M 独立判定](M-acceptance-r1.md)
- [I 冻结候选](I-candidate-r1.json) 与 [成本账](I-cost-r1.json)
- [最终独立验收](acceptance-r1.md) 与 [原始证据](acceptance-evidence-r1.json)

本轮交付限 K2a；剩余 K2 仍未实施。无自动提交，biomiya 工作区和既有迁移由原任务保留。
