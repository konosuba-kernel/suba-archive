# 推进至 K7

2026-10-15。用户授权：按原 K1–K10 大环节持续推进至 K7；强依赖内部工作由同一实施者连续完成，不拆成过多子代理；每个环节独立验收通过后提交一次。此授权覆盖旧文档的“本轮不自动提交”。K1 按已接受范围修订继续延期，不因编号顺序恢复磁盘部署要求。

已接受起点：K0、K2a、K2b；K2b 提交 `7712dd3`。规范沿用 `design/IMPLEMENTATION.md`、`design/CONTRACTS.md`、`design/ARCHITECTURE.md`、`CODE_STYLE.md`，不以局部演示降低大环节门槛。

执行图：`K0 → K2 → K3 → (K4 ∥ K5) → K7`，`K0 → K6 → K7`。K4/K5依赖完整K3，K7汇合K4/K5/K6。K8–K10不在本轮完成范围。

| 阶段 | 必需成果/验收 | 实施与写入范围 | 独立验收 | 状态/提交 |
|---|---|---|---|---|
| K2 | Sv39、ELF加载、完整U现场、定时抢占、应用故障隔离、创建失败回滚/回收；真实QEMU与必要反例 | /root/memory_resume；kernel/space/process/loader/machine/entry、K2 tests/tools、boot运行清单；必要ABI由root串行协调 | root（验收新增实现；既有RAM已独立验收） | K2-r1 独立验收通过；提交见 Git 历史 |
| K3 | 句柄/等待/退出/用户库、跨页usercopy、权限、EOF/背压、父子取消、统一回收 | /root/memory_resume；kernel对象/请求/系统调用、user/libsuba、K3 tests/tools；root为前期草稿贡献者 | /root/ram_acceptance（已派发） | K3-r1 已接受，提交 `6162887` |
| K4 | virtio block/IRQ/FLUSH、真实盘持久FS、正常重启、写满回滚、DMA取消收尾 | root 与 /root/k4_filesystem；kernel/device/virtio/block、kernel/fs、tools/mkfs、K4 tests | /root/k4_acceptance | K4-r1 已独立验收通过；提交见 Git 历史 |
| K5 | 输入、ramfb、窗口/事件、受保护desktop、实际键鼠和可重叠窗口 | /root/ram_fdt（早期探索）、/root/k5_windows（接续）；device/input/display/window、user/desktop/draw、K5 tests | /root/k4_finish 执行，/root/k4_review 接续判定 | K5-r1已独立验收，提交 `92c76d2` |
| K6 | UTF-8、4MiB编辑核心、中文字形/缺字、许可及原生fontpack；K7前不声称完整UI | /root/ram_fdt；user/text、user/edit核心、tools/fontpack、assets、K6 tests | root | K6-r1 独立验收通过；提交见 Git 历史 |
| K7 | 实际系统内编辑保存→冻结快照→编译诊断→运行，另窗响应，取消/坏产物不发布，无宿主文件服务 | root；共享dispatch/清单、editor/build集成、初始盘及K7 tests | /root/k4_review（未参与K7实现） | K7-r2功能闭环已验证，整体indeterminate；按用户新指示保存进度提交 |

各阶段候选按文件哈希/依赖commit冻结，再独立验收；失败保留记录、增加revision。每阶段只保留必要的简明报告、复现脚本和日志身份，原始大日志在build中，避免重复整份海量JSON。提交仅包含该阶段已验收范围；并行阶段未验收改动不得夹带。阶段内部不为每个helper/interface再建agent节点。没有真实验收就保持未完成。

派发检查：依赖图无环，K2与K6写入范围互斥；根调度独占本日志和全局设计导航。所有执行者禁止自行提交；root在验收后精确暂存并提交。不得以缩小需求/放宽测试或伪造标记跨过门槛。

执行更新：K6提交 `3cceb87`，K2提交 `72e19fb`。K3正式沿用K2实施者，root前期草稿仅是输入，不冒充通过证据；独立验收仍归未参与者。K4/K5所需的共同virtio transport由K4唯一维护，正式接入时按冻结接口串行协调，不维护两套通用驱动。

### C64：K4/K5 的编译器容量前置

实际K3清单已达30个VT；K4的transport/block/FS codec/挂载与worker至少新增4个独立模块，超过现行32源文件上限。增加一个必要工具链支持节点，不通过合并模块掩盖容量边界。C64依赖已接受的biomiya `d2c6e98` 与旧e3（SHA256 `049c6e094ccd044fba3b5d357583013b77f0e8e9a98d431ad919e02b0cda2144`）；与K3并行，不改K3当前编译器输入。K4/K5正式集成使用经独立接受的新e3。

C64作者 `/root/ram_fdt`，独立验收root。允许写biomiya/compiler的容量相关三个文件、相关tests/tools、当前版本参考、docs/history/source-cap64；禁止冻结bootstrap/历史证据/语言语义/其他容量/ suba生产。实现完整32→64源容量及重置，统一使用SOURCE_CAP判界（数组长度亦直接由 SOURCE_CAP 派生）；保留1MiB宿主栈、源总量/assembly数量/prepare_depth边界。要求32/33/64成功、65精确失败无产物、64VT+8S0与末端诊断、64模块链/环、两轮headers清零、完整自举E2==E3和扰动证据、相关语言/limits/machine/profile/reference回归；报告增加的表/ELF成本。候选按源码/工具/依赖/ELF摘要冻结，root独立判定后单独在biomiya提交。当前状态：C64-r1 已独立验收并提交 biomiya `bd73055`。新 e3 SHA256 `22d2c81fd0dbfc6de6b3b13fb2f485b1c64913849d9e59eeabe8c2757d27ebf4`，可供 K4/K5 使用；验收记录见 `biomiya/docs/history/source-cap64/acceptance-r1.md`。完整自举证据经哈希核验，独立边界用例通过，新编译器重建 K2 与已接受 ELF 逐字节相同。

用户补充（2026-10-15）：阻塞/难点/BUG持续记录，供语言与架构改进。总索引`docs/engineering/README.md`；各作者维护本阶段engineering-notes并纳入候选，root维护全局索引和历史回填。不将语言规则/平台限制/测试错误混称实现缺陷，保留失败与修正证据。

K3-r1 冻结于 2026-10-15：candidate SHA256 `49c0d6c1639e5782bccef6b283018fceb3c724c8ac0e2eb0e9f401d5725f4a44`，51 owned files / 20 inputs；独立验收已派发 ram_acceptance。源码停写，性能目标与功能门槛分别报告。

K3-r1 独立判定通过：16 个功能/故障恢复场景和 3 个负控均符合预期，详见 K3-acceptance-r1.md/json。5ms 目标部分未达，其余系统交互指标未测，不能包含在功能通过结论。K5 root 将参与共享接入，独立验收调整为未参与K5的 memory_resume，避免自审。

K3 提交 `6162887`；K4 正式开始。共同 transport/io 是 K4 内部接口交付，由原 K4 验收者先独立核验冻结版本后供 K5 使用，不另拆实施agent。K5 的公共状态/清单接入在 K4 提交后串行集成，避免两个未验收阶段混入同一核心文件。

### 执行上下文恢复

2026-10-15：恢复后工具仅报告 root 活跃，原 ram_fdt/ram_acceptance/memory_resume 不再可用。保留各阶段既有贡献与验收身份；新派发 `/root/k4_filesystem` 接续 K4 文件服务及核心接入，root 仍是 K4 贡献者，不能自验。`/root/k4_acceptance` 独立核验冻结 transport，之后负责完整 K4/K7 验收；`/root/k5_windows` 接续 K5 新模块，既有核心文件仍由 K4 唯一写入，K4 提交后 root 串行接 K5。K5 最终验收再派未参与实现者。旧候选和证据不因上下文恢复自动作废，也不因文件存在追认通过。

K4 生产挂载测试 `build/k4-protected-mount-r1/verification.json` 已通过：同一受保护内核运行 U 程序，真实设备挂载与 boot serial 的 FLUSH/正常重启读回。文件系统调用、容量/取消/回收尚未完成，该测试不构成 K4 完整验收。

共同 transport r1 已由 `/root/k4_acceptance` 独立通过，报告 `K4-transport-acceptance-r1.md/json`。K5 正式消费候选 SHA256 `fd2845d4ef845db84e8188c9fd78cc5c468709e21597f954d3542027c43ea0ac` 的原始 io/virtio 文件；此内接口验收不等于整个 K4 通过，不单独代替阶段提交。root 的 `tools/check_mkfs.py` 在 `build/k4-mkfs-r1` 通过15例；`tools/check_fs_metadata.py` 在 `build/k4-metadata-r1` 通过128例，均明确限定为host格式/原生纯校验器，完整guest文件服务仍待实施。

2026-10-16 再次恢复：工具仅列出 root，已派发 `/root/k4_finish` 接续 K4、`/root/k5_finish` 接续 K5、`/root/k4_review` 负责未参与实现的 K4/K7 独立验收。既有贡献、通过及失败记录继续保留；root 增补真实坏盘与设备错误测试，不自验 K4。

K4-r1 于2026-10-16冻结，candidate SHA256 `767ff03e757cb707b7ae81ff05fb3b5afe652af7595db760901e80c9491d4105`；84 owned files，独立验收 `/root/k4_review`。生产kernel为filesystem-r5，两个真实所有权BUG已修，测试失败与模型行为均保留。DELIVERY仅协调日志，不纳入冻结源码输入。K5仍未验收，不夹带其新模块。

K4-r1 完整独立验收由 `/root/k4_review` 通过，报告 `K4-acceptance-r1.md/json`：干净重建全字节相同，真实文件持久化、故障拒绝、所有权反例和200轮DMA取消回收通过。root仅提交候选84项、候选及验收记录与协调日志；K5未验收文件排除。K5独立验收绑定 `/root/k4_finish`（仅贡献K4，未贡献K5），root接续共享核心集成。

K4提交 `10de32f`。K5共享接入基于该提交，由root负责dispatch/request/objects/process、hub/entry及清单；仅boot image 0授可信desktop。新窗口模块仍由 `/root/k5_finish` 维护，避免并写。首次生产组合探针 `build/k5-integrated-contracts-r1` 在编译；此前K5隔离快照不自动算作当前组合证据。

K5-r1 于2026-10-16冻结，candidate SHA256 `7d86276770c2d6b64c0a2df1edf696836640c38a5f8917e7abafa255e602442b`；52 owned / 120 inputs，基线 `10de32f`。独立验收 `/root/k4_finish`，范围为 K5 增量及其组合行为；K4 本身沿用 `/root/k4_review` 的独立结论，不由 K4 作者自验。当前候选真实 GTK 八阶段、102轮窗口生命周期、100事件队列和两次启动共200轮 DMA 取消已留证；实际重绘仍为秒级，性能目标未达。K7只保留探索草稿，待K5接受后正式启动。

K5-r1 验收执行中 `/root/k4_finish` 触发工具端 usage limit，在最终判定落盘前异常结束。其独立目录 `build/k5-independent-r1` 已留存哈希核对、GTK/contracts/lifecycle/queue/usercopy及旧BUG负控结果，但不能由root代签结论。已派 `/root/k4_review` 接续独立检查与判定（未参与K5实现）；候选仍冻结，尚不提交/正式启动K7。

K5-r1 已由 `/root/k4_review` 接续独立验收通过，报告 `K5-acceptance-r1.md/json`；原独立执行者全部已完成日志保留。功能依赖解除，性能目标未达，不改写为30fps/100ms达标。精确提交52 owned、候选、独立报告与协调日志，K7草稿及工程记录不夹带。

K5提交 `92c76d2`。K7正式开始：`/root/k5_finish` 独占内核/FS/Job/spawn及纯ELF提取和kernel专项测试；root独占U态build/editor、编译器host适配、组合工具/测试、全局设计导航。阶段内部只有这两个可分离写入边界，最终整体验收 `/root/k4_review`（未贡献K7）。实现中接口先协调，阶段接受前不提交K7。

K7-r1候选已冻结并进入独立验收，生产组合system-r4。最终GTK first完整编辑/编译/错误/取消后，重启同盘panic70，阶段转返工；r1未通过、不提交。k5_finish修复内核持久化，root修证据字段和panic观测；k4_review保持独立审查，修后r2重验受影响范围。

K7-r2已冻结，candidate SHA256 `64e4b379527cb24564115cab9ac8934dc398cc8e0ef9d388c9351dd96089cc69`，
83 owned/102 inputs。最终system-r5的真实GTK完整闭环及同盘重启通过，原失败盘、临时状态回收和
真实坏盘对照通过；独立审查已覆盖这些行为。新增回收专项曾一次第二次重启panic70，盘元数据
Valid且已写启动序号，12次诊断重放未重现。此项与K4正常重启依赖相关，不能以K10未完成为由
忽略；目前独立整体验收无法判定，继续做并发I/O与失败分支观测对照，暂不提交。

K7-r2最终独立判定为 **无法判定整体通过（indeterminate）**，报告K7-acceptance-r2.md/json。
功能闭环、原确定性缺陷修复、真实坏盘拒绝及回收均已有区分证据；12次失败分支诊断与6次受控I/O
对照未复现，不足以归类那次正常启动panic70。按用户“环节验收后提交”及独立验收规约，K7不接受、
suba与biomiya均不提交此轮修改。候选和证据保留，后台测试已结束，没有隐藏运行的后续任务。
最终独立报告SHA256：md `1d791aa7d76f23442a9baffbade747bf4fa0d6ab28e50585a51645f2cf22a90c`；
json `9411b5247ea8ddaa63ad8c30f1cba817305fa9b7e7f57fd06f91ec2f58f8eebf`。

### 用户授权的进度提交

用户在独立判定后明确要求“记录阻塞问题，提交目前进度”。据此保存当前 K7-r2 实现、测试和
文档，不再以阶段通过作为本次进度提交的前提；**不改变 K7 未整体验收的状态**。此前“不提交”
是当时决定，原候选、证据摘要和独立报告保持原样，避免改写验收历史。

当前阻塞与接续条件集中在 [BLOCKERS](BLOCKERS.md)。主阻塞为 K7-K06 的未归类正常重启
panic70；早期 Job DMA 第61轮 code100 同样保留。源码与冻结 r2 的185项owned/input身份
在提交前核对一致，本次仅补阻塞说明和协调/导航，不重新宣称测试通过或启动新实现。

编译器配套进度已提交 biomiya `65cb036d1279975dd01d8aee248c6cf0612c8b92`；suba进度对应
包含本条的Git提交。两个仓库均为进度保存，不是K7 accepted里程碑。原始磁盘、ELF和大日志
仍留在ignored build目录，不加入Git；生产源码、回归入口及报告随提交保存。

### 后续 K7-r3 验收

在进度提交 `49b2213` 之后，按用户新授权继续排查。K7-r3 已独立验收并提交为
`08a4d07`。详见 [K7-acceptance-r3](K7-acceptance-r3.md)；早期未归类样本和旧判定保留，
新的确定性通知处理修复及回归不能倒推早期故障的根因。下游由
[推进至 K10](../through-k10/DELIVERY.md)接续。
