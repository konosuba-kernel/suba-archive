# K7 实施报告

候选 K7-r1；作者 root（用户态/编译器host/组合）、k5_finish（内核/文件系统/Job）。
独立验收者 k4_review，判定另见 K7-acceptance-r1。基线 suba `92c76d2`、biomiya `bd73055`。
本报告列实施证据，不代替独立判定。K7-r1因最终GTK重启panic70退回返工，不能视为已交付。使用入口见 ../../K7_RUN.md。

## 交付

- 普通应用从真实 guest 文件系统装载。仅可信 desktop 保留 RAM 启动入口。
- 编辑器显示 UTF-8 和中文字形、编辑/原子保存、调用构建、定位有效诊断、运行当前已发布版本。
- build 在 Job 中复制输入、记录哈希、冻结权限，启动普通 U 态 S-next 编译器；诊断经过流返回。
  正常结束后校验 ELF，原子替换发布；失败和取消保留之前的完整产物。
- Job 的后代继承受限目录权限；旧句柄不能绕过冻结。退出、强杀及迟到 DMA 使用同一回收路径。
- biomiya 增加 host_suba，前端/分析器/后端共用现有实现；ReadResult 明确表达 TooLarge，消除
  input/Blocking 对 Linux 私有错误17的依赖。
- build_system 保存源快照、编译身份、初始磁盘；run_system 使用已有磁盘，不会重新格式化。

## 实施验证

最终系统 `build/k7-system-r4`：kernel SHA256
`0dc8ef589248f4b6845607346b933ff7f592fba67b1b74680554d72db2ef981d`，
编译器 SHA256 `872580a5751997a32c7b91c127987117e375a866fa99ecb36292ab443d0bb63c`。
种子为 C64 E3 `22d2c81fd0dbfc6de6b3b13fb2f485b1c64913849d9e59eeabe8c2757d27ebf4`。

| 证据目录 | 实际覆盖 |
|---|---|
| k7-planner-r1 | 69例原生RV64路径、上下文、SHA互操作 |
| biomiya/k7-host-input-r1、host-io-r1、host-blocking-r1 | 26/12/48例当前Linux消费模块回归 |
| k7-kernel-final-evidence.json | 最终内核专项身份索引；权限、映像、发布、死亡及取消 |
| k7-kernel-job-owner-r1 | 10轮创建者死亡/隐式Job关闭/子树回收 |
| k7-kernel-load-cancel-r3、job-dma-r3 | 各100轮装载或Job磁盘等待取消，恢复基线 |
| k7-kernel-job-r3/freeze-seal-comparison.json | 相同U ELF，旧内核失败/修正内核通过 |
| k7-kernel-no-user-irq-r3 | 同U ELF、关闭U外部IRQ的负控触发预期panic73 |
| k7-pipeline-r4 | 真实编译、运行41、错误保留、取消、页/流回收，122.92秒 |
| k7-pipeline-invalid-r3 | 返回成功但输出坏ELF的编译器被拒绝，旧发布字节保留 |
| k7-pipeline-r4/persistent-verification.json | guest ELF与独立Linux oracle完整相等，12289字节，无遗留Job |
| k7-desktop-r1 | 首段编辑/构建/运行/诊断/取消通过；同步后同盘重启panic70，整套失败 |

以上相对目录均在各仓库 build 下，原始日志不纳入Git。候选/证据摘要与独立判定保存在工作流。
pipeline-r4/invalid-r3 的记录字段 compiler_sha256 被工具后续的guest产物身份覆盖，实际为
872580…；种子22d2…由commands、system验证记录与编译器实物核对，不能误当成换了种子。
正式system-r4复用r3的build/compiler时逐项检查所有输入哈希与产物；二者不同的是最终UI对齐修正。

## 规模及限制

按手写 `.vt/.s0` 物理行（含注释/空行，不含字体生成数据、测试及工具）计：kernel 53文件8907行，
abi 7文件516行，platform 5文件680行；build 8文件1011行，edit含K6核心9文件1300行，libsuba
8文件553行，desktop 1文件386行。此分组不把测试或运行支持冒充零成本，也不表示总仓库规模。

最终用户ELF/实际PT_LOAD内存字节：compiler 1061008/56192346，build 274464/21378199，
edit 393240/14534446。静态缓冲和BSS的分配清零是实际装载成本。

交互仍为秒级；脏行上传和像素对齐修正不等于30fps或100ms性能目标达标。当前不含输入法、复杂
排版和电源管理UI；GTK持久化验证是guest保存并同步、作业收尾后停止QEMU，再从相同磁盘重启，
不是突然断电恢复或完整系统正常关机协议。编译器固定点属于K8，内核/S0原生重建属于K9，均未完成。

早期Job DMA测试第61轮出现一次code100失败，原因未明；同ELF两次重跑、诊断重跑和最终增强测试
均通过100轮，不能据此宣称已经修复该次失败。失败原件与其他编译/测试/观察器错误保留在工程记录，
供后续语言与架构改进。K7不是稳定性或性能最终验收。
