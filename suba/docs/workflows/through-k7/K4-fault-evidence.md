# K4 真实存储拒绝与设备故障

2026-10-16，root 实施；这是完整 K4 的输入证据，不是独立验收。复现入口 `tools/check_k4_faults.py`，说明 `tests/k4/faults/README.md`。

`build/k4-faults-r1/verification.json` 已通过 11 例：正常控制；CRC 损坏；重算 CRC 后不合法的布局；节点名非法 UTF-8；数据 FAT 环；挂载元数据读 EIO；启动序号写 EIO；挂载 FLUSH EIO；运行期数据写 EIO；运行期元数据写 EIO；运行期数据读 EIO。生产代码来自 `build/k4-filesystem-r3` 冻结快照，报告保存精确 ELF 身份。

这些是预期拒绝，没有发现“设备错误被当作成功”的缺陷。挂载失败返回 panic 70，运行期驱动完成失败返回 panic 71；测试必须观察对应 panic，不能以 QEMU 退出或宿主超时替代。每例独立初始盘，运行期错误还必须先证明挂载完成。正常控制证明同一 fixture 无故障时能走完整读写、同步、退出回收路径。

难点在于故障必须命中实际阶段：普通 blkdebug 的首次写错误会发生在启动序号持久化，不能拿它声称运行期元数据失败已测。这里分别按 512 字节扇区定位 superblock、FAT 和数据区，并核对串口阶段。QEMU `immediately` 表示立即拒绝请求，并不等于请求超时；完成超时采用另一个测试快照屏蔽 PLIC 设备完成，保留原驱动超时判断。

限制：不验证突然断电后的事务恢复，该能力仍在范围之外；EIO 与完成超时也不模拟所有可能设备故障。后续架构可考虑更具体的存储 phase/operation 诊断，目前通用 panic 数字只能定位到挂载、驱动服务或 FS worker 边界。

`build/k4-faults-r2/verification.json` 完成 12 例并全部通过：重复上述 11 例，同时验证挂载后真实设备完成被屏蔽时，未修改的 block deadline 使 FS worker 返回 panic 73。该例仅给测试快照 hub 加屏蔽入口，在启动 U 进程前执行；中断/时钟服务和生产超时判断保持原逻辑。报告校验冻结源码并保存所有启动产物摘要、超时探针的编译输入和 ELF 身份。

独立审查后的证据细化：原 `data_read_eio` 的扇区194可能在 partial write 的边缘读取阶段就命中，因此它只证明运行期驱动 Read 错误停机，不能单独声称已验证用户 FileRead。新增 `tests/k4/faults/read.vt` 无任何前置写入，直接读取初始文件的193块；`tools/check_k4_read_fault.py` 在 `build/k4-file-read-fault-r1` 对同一冻结内核运行健康控制与193块 read EIO，均符合预期。旧报告保留，不改名冒充新覆盖。

生产权限/cwd 修复后的复核：`build/k4-faults-r3` 在 `filesystem-r5` 的 kernel `87451fecfd59ed3df7f64f2a6e15e19448b1990ec7ed2274eb724ca14e405127` 上重跑11例，全部符合预期；专门 FileRead 控制/故障在 `build/k4-file-read-fault-r2` 同样通过。旧 timeout 快照不冒称新版本，最终指定 DMA 的 SEIE-off 负控另核对最新生产路径。
