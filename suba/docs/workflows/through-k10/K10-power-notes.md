# K10 电源状态机探索

状态：探索中，尚未接入生产、尚未独立验收。生产依赖保持 K7 `08a4d07`；K8/K9 正在绑定冻结源码。所有内核改动只发生在 `build/k10-power-prototype*`。作者 `/root/k5_finish`，不得以本记录作为 K10 通过结论。

## 接口与生命周期

沿用既有 `SYS_POWER=66`：参数依次为 Desktop handle、action（0 关机，1 冷重启）、四个零。对象所有者增加专用 POWER 权（32）；身份仍必须是唯一可信桌面。普通应用即使猜出相同整数 handle 也不能请求电源操作；普通 kill 的桌面保护不变。错误权限返回 Denied，非法 action/reserved 返回 Invalid，已接受的重复请求返回 Busy。

第一次请求在串行 dispatch 点进入单向 stopping 状态，并将返回帧设为 OK/0；桌面可能在下一次 U 调度前已经结束，因此不能依赖返回后执行任何保存。桌面入口必须先保存并明确未保存缓冲的处理政策。SBI SRST 成功不返回；返回值一律进入 panic，而非当作成功。

状态依次为 Ordinary（每步结束一个普通进程）、Desktop（等待普通进程完成回收再结束桌面）、Drain（等待进程/stream/child/Job 所有者归零，物理页恢复启动前基线）、Flush（现有 fs::shutdown_step 排空已提交事务、DMA、临时节点，SyncAll/FLUSH）、Ready（执行 SBI）。冻结后拒绝新 spawn、Job、分配、写请求和命名修改；已提交 FS 事务及清理继续推进。最终 FLUSH 的失败保持可观察停机，不执行 SBI。

trusted desktop 的 framebuffer 映射是借用永久 BSS 的页，不属于普通页分配器。专用内部 shutdown_desktop 先授权 Dying，原有 abort_display_step 分片取消借用叶映射并扣除计费，再复用普通进程回收。不能直接把 trusted guard 去掉，或直接把 framebuffer 页交给 allocator。

新增 `dispatch_power.vt` 后是 64 个 VT 输入，达到当前编译器容量；不拆碎模块以隐藏容量问题。COMMON/ABI/compiler 源身份未改。将来用户包装器可放独立可选 `libsuba/power.vt`，不进入 compiler COMMON。

## 已完成证据（探索版本）

- `build/k10-power-prototype-r1/verification.json`：宿主构造锚点错误，未编译、未进入 guest。保留为装置失败。
- `build/k10-power-prototype-r2/verification.json`：真实 SBI shutdown，3.01 秒，QMP guest-shutdown、QEMU exit 0、无 host terminate。
- `build/k10-power-prototype-reboot-r1/verification.json`：真实同 QEMU cold reset 后 boot=2 读取已保存文件，再真实关机，8.26 秒。包括普通进程猜测电源 handle 被拒绝。
- `build/k10-power-prototype-busy-r1/verification.json`：Frozen Job、阻塞 stream 进程、未关闭 Transient 文件与真实 Submitted 写 DMA 下接受电源请求；实际 IRQ 释放后排空，回到物理页基线，重启读取再关机，8.69 秒。观察者仅暂停 PLIC enable，不伪造 used entry/完成事件。该 ELF 含测试观察器，不等同基本原型 ELF。
- `build/k10-power-prototype-eio-r1/verification.json`：最终 FLUSH 真正返回 EIO，reason=6、command=4、status=1、used=consumed+1；未打印 flushed，无 QMP SHUTDOWN，sbi_success=false。passed 只表示故障预期满足。
- `build/k10-power-prototype-timeout-r1/verification.json`：最终 FLUSH 延迟 1.2 秒触发现有 1 秒 watchdog，reason=7、status=255、used=consumed；未执行 SBI。没有扩大 deadline。停止故障 VM 的 host terminate 只是失败后的测试清理，不是成功关机。

追加只读证据 `build/k10-power-prototype-disk-ledger.json` 核对 reboot-r1 与 busy-r1 停止盘：7→8 节点、21→22 数据块，唯一新增文件是全字节 `survived`，所有原文件 SHA 保持，flagged=0。它独立引用原 verification 的 SHA，不改写旧记录。

这些初轮成功仍未覆盖 pending Loading 的父子取消顺序，磁盘读取原先仅检查首尾字节。新修订将检查全字节、节点/FAT 账本和取消竞态；不得将新断言倒算给旧报告。

## P01：关机过程与 pending spawn 的顺序风险

分类：新原型的静态发现，待确定反例；不是既有生产缺陷。

普通进程按槽逐个 terminate 时，低槽 Loading 子进程可以先进入 Dying，高槽父进程的 spawn request 仍在下一 dispatch 片推进。process::load_request(Dying) 可能进入 panic22。拟在 stopping 期间暂停普通 request advance，继续 IRQ/FS/reaper；请求随后由其所有者的正常死亡清理取消。真实 Loading 子进程低于父槽的受控 DMA 观察器将比较有/无保护，结果随后记录。

启示：单向停止不是只加入口门禁；已接受的复合请求也必须在同一生命周期规则内停止推进。应通过既有所有者取消，不另设一套手工释放表。

## 装置错误记录

Loading observer 首轮 `loading-old-r1` / `loading-new-r1` 在宿主编译报 E_NAME，原因是测试直读私有 process::Id.slot。改用公开的 process::slot；两个原失败目录保留，未进入 guest，不属于内核运行错误。私有字段检查保护了身份所有者边界。

## 正式接入包与后续命令（尚未启动）

`build/k10-power-prototype-integration-r1/production-delta.json` 列出每个基线/结果 SHA 及绝对复制来源；同目录 `production-delta.patch` 是可评审的十二文件补丁。新模块之外的改动分布为 dispatch 入口/暂停请求、objects 专用权、桌面身份/借用显示页回收、现有 FS shutdown 结果检查、entry 协调、SBI scalar wrapper。包无 DMA/调度观察器；标记 compiled=false，正式接入须重新构建。模板只做了缩进/注释整理，语义与新 guard 探索相同。

`check_k10_shutdown.py --production` 会直接快照生产实现，不调用 prototype()，也不允许 --unguarded；COMMON 不变。busy/loading 只加入明确的测试观察器。正式 K10 启动后可执行如下顺序（目前仅计划）：

```sh
python3 tools/check_k10_shutdown.py --production --compiler ../biomiya/build/source-cap64-p4-r3/e3.elf --out build/k10-power-production-shutdown-r1
python3 tools/check_k10_shutdown.py --production --compiler ../biomiya/build/source-cap64-p4-r3/e3.elf --action reboot --kernel-from build/k10-power-production-shutdown-r1 --out build/k10-power-production-reboot-r1
python3 tools/check_k10_shutdown.py --production --compiler ../biomiya/build/source-cap64-p4-r3/e3.elf --scenario busy --action reboot --out build/k10-power-production-busy-r1
python3 tools/check_k10_shutdown.py --production --compiler ../biomiya/build/source-cap64-p4-r3/e3.elf --scenario loading --force-order --action reboot --out build/k10-power-production-loading-r1
python3 tools/check_k10_shutdown.py --production --compiler ../biomiya/build/source-cap64-p4-r3/e3.elf --fault eio --kernel-from build/k10-power-production-shutdown-r1 --out build/k10-power-production-eio-r1
python3 tools/check_k10_shutdown.py --production --compiler ../biomiya/build/source-cap64-p4-r3/e3.elf --fault timeout --kernel-from build/k10-power-production-shutdown-r1 --out build/k10-power-production-timeout-r1
```

原型参数保留，可重现旧版本与明确 `--unguarded` 负控；正式入口绝不移除生产 guard。真实桌面热键由 root 在正式 K10 接入，另作产品入口验证。

### Loading 自然路径与装置定位

`loading-old-r2` / `loading-new-r2` 未进入 SYS_POWER，fixture code16；`loading-new-r3` 细分为 DMA 标记未出现，code38；`loading-new-r4` 收集到 loader 自行退出 status10（open(go) 非 NotFound 的分支）。握手允许 Busy 重试后，`loading-old-r3` 与 `loading-new-r5` 都到达 child=1、parent=2 的真实 Loading DMA 等待点并成功。new-r5 完成同 QEMU reboot、全字节和节点/FAT 账本检查。两边自然路径均通过，不能称已复现静态竞态。

为覆盖缺少的合法交错，`--force-order` 仅在真实子进程终止后指定下一 dispatch 的 cursor/轮询相位，使它选择尚未终止的 Loading 父进程；不直接调用 advance，不改请求、身份或 used entry。受控调度证据必须与自然运行分开列出。结果待补。
