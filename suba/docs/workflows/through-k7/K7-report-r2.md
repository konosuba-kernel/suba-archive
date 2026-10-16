# K7 实施报告（r2）

**K7尚未整体验收、未提交。**系统内编辑→保存→冻结快照→编译→诊断→运行闭环及同盘重启已在最终组合完成，但另一次合法盘启动的panic70仍未归类。
阶段是否接受以 [独立验收](K7-acceptance-r2.md) 为准；[运行入口](../../K7_RUN.md)。
作者 root（用户态、host、组合）与 k5_finish（内核）；独立验收 k4_review。
基线 suba `92c76d2`、biomiya `bd73055`；候选身份见 K7-candidate-r2.json。

## 最终行为

只有可信desktop从RAM引导；编辑器、构建工具、编译器和生成应用均从真实guest FS装载。
编辑器支持UTF-8/中文字形、编辑保存、有效诊断跳转和运行当前已发布版本。构建工具复制并记录
输入身份，冻结Job权限，再启动普通U态编译器。成功退出且ELF有效才原子发布；失败或取消保留旧
产物。作业后代继承受限权限，终止时排空请求并回收。没有宿主运行期文件服务。

biomiya新增host_suba，复用原编译器核心；host的ReadResult具名表达TooLarge，Linux私有错误17
仅在Linux适配层解释。目标profile与编译器运行环境分开，没有另复制一套前端或后端。

r1真实GUI在同步保存后重启panic70，已明确不通过并保留原盘/报告。r2修正合法持久状态的挂载：
完整校验包括Transient/Detached在内的全部节点、父链、块链及所有权，再分片回收无跨启动所有者
的临时版本，写回FLUSH后Ready。Detached不算可见同名冲突；目录删除等待其Detached子项回收。
真实坏链仍拒绝，不能先GC掩盖损坏。这不是突然断电事务恢复。

## 可复核证据

最终组合 `build/k7-system-r5`，内核SHA256
`2f073509c6af8bce081ec60927e82db836b40fc678582ed0b831903efef88bd3`。
编译器产物SHA256 `872580a5751997a32c7b91c127987117e375a866fa99ecb36292ab443d0bb63c`；
宿主种子C64 E3为 `22d2c81fd0dbfc6de6b3b13fb2f485b1c64913849d9e59eeabe8c2757d27ebf4`。
r2全部U ELF与r1正式system-r4相同，仅内核修复改变生产组合；复用时逐文件验证输入和产物。

| 证据（各仓库build下） | 结果及范围 |
|---|---|
| k7-planner-r1 | 69例原生RV64规划/路径/SHA互操作通过 |
| biomiya/k7-host-input-r1、host-io-r1、host-blocking-r1 | 当前Linux模块26/12/48例通过 |
| k7-kernel-final-evidence.json | r1权限、映像、发布、死亡及100轮装载/Job DMA取消；r2是否复用由独立验收明确 |
| k7-kernel-remount-build-r1 | 修正内核重新通过原子发布 |
| k7-remount-metadata-r1 | 141例纯生产codec/validator正负例通过 |
| k7-kernel-remount-malformed-r1 | 三种真实坏盘均panic拒绝，盘字节未变，未被GC掩盖 |
| k7-kernel-recovered-r1 | 原失败盘在新内核启动及再次两轮启动通过，published文件不变 |
| k7-kernel-remount-r2 | flags1/2/3回收、65块分片、目录Busy/关闭后可删、两次重启；内存与持久节点/FAT账本一致 |
| k7-pipeline-r5、pipeline-invalid-r4 | 真编译/运行41/错误保留/取消/回收，以及成功退出却产坏ELF拒绝，均通过 |
| k7-desktop-r2 | 22个首轮GTK阶段及4个重启阶段通过；实际键鼠，无guest内存写入 |

GTK实际将41改42，编译运行；编译时另窗保存；错误源码诊断、准确跳转、过期拒绝、未保存关闭
保护、取消；最终guest同步后停止QEMU，核对源码/notes/ELF及无遗留Job，再复制同一盘重启并运行42。
生成ELF12289字节，SHA256 `65a8ed06c8a996f434d109c0729b2071cd3805bc1e852d2c620853cfb01b8e66`，
与相同输入的Linux oracle逐字节相等。重启没有注入新的程序或替换文件。

候选/最终证据摘要/独立报告保存在工作流；原始大日志在ignored build。旧K2–K5的RAM应用fixture
需在其历史提交或冻结快照重放，不能冒充最新组合回归。r1 pipeline的compiler_sha256字段覆盖
问题保留记录；r2已分开seed与guest字段。

## 成本与未完成项

按手写VT/S0物理行（含注释空行、不含字体数据、测试/工具）分别计：kernel 53文件8975行，
abi 7文件516行，platform 5文件680行，build 8文件1011行，edit含K6核心9文件1300行，libsuba
8文件553行，desktop 1文件386行。这些是分组数，不宣称为完整仓库总规模。
用户ELF/实际PT_LOAD内存字节：compiler 1061008/56192346、build 274464/21378199、
edit 393240/14534446；BSS分配清零是真实成本。

最终GTK首次构建145.92秒，编译背景下另窗聚焦编辑保存合计29.06秒。该运行与其他验收并发，
不是隔离性能基准；仍明显未达到100ms/30fps目标。K8原生编译器固定点、K9内核/S0原生重建、
K10整系统性能/稳定性均未完成。无中文输入法、复杂排版和电源管理UI；本次重启边界是guest显式
同步后停止QEMU，不宣称完整正常关机协议或突然断电恢复。

两项失败必须保留：早期Job DMA第61轮code100未解释；r2新增回收专项r1曾一次第二次重启panic70，
其盘纯校验Valid且已写启动序号。后续同输入重放通过不能证明找到原因。后者失败分支诊断结果见
K7-kernel-notes及独立判定。工程记录区分已修根因、未解释失败、工具错误及后续语言/架构改进建议。

最终诊断快照12次及受控I/O竞争6次均未重现异常；后者host fsync最大1.36秒，但没有失败分支证据，
不能证明历史panic是设备超时。独立判定保留这条正常重启前置合同的窄阻断，不以K10未完成豁免。
