# K4 common transport r1 独立验收

结论：**通过**。仅接受现代 virtio MMIO split queue 与 io 标量机器访问接口，不接受完整 K4。审查者 `/root/k4_acceptance`，接替原 `/root/ram_acceptance`；未参与生产实现。2026-10-15。

候选：`K4-transport-candidate-r1.json`，SHA256 `fd2845d4ef845db84e8188c9fd78cc5c468709e21597f954d3542027c43ea0ac`。基线 suba `6162887`；C64 biomiya `bd73055`，e3 SHA256 `22d2c81fd0dbfc6de6b3b13fb2f485b1c64913849d9e59eeabe8c2757d27ebf4`。开始、独立探针构建和完成时均核对 8 owned + 2 inputs，全部一致。候选里的旧 reviewer 名仅是角色计划，实际判定者为本报告署名。

## 执行证据

在 suba 根目录执行（各输出目录首次运行时不存在）：

```sh
python3 tools/check_transport.py --compiler ../biomiya/build/source-cap64-p4-r3/e3.elf --out build/k4-transport-independent-real-r1
python3 tools/check_transport.py --compiler ../biomiya/build/source-cap64-p4-r3/e3.elf --out build/k4-transport-independent-noirq-r1 --no-irq
python3 tests/k4/independent_transport/check.py --compiler ../biomiya/build/source-cap64-p4-r3/e3.elf --out build/k4-transport-independent-boundaries-r2
python3 tests/k4/independent_transport/check.py --compiler ../biomiya/build/source-cap64-p4-r3/e3.elf --out build/k4-transport-independent-mutant-r1 --omit-duplicate-guard
```

| 验证 | 实际结果与区分力 |
|---|---|
| 真实 QEMU block | 两次正常 SBI SRST shutdown，每次 65,544 次等待 trap handler 增加 IRQ 计数之后才消费 used ring；完成读、写、FLUSH、16 位索引回绕，第二次启动读到第一轮写入标记。两次进程返回 0。 |
| 禁止 SEIE | 仅改快照中 IRQ enable 的 512 为 0；4 秒宿主超时，客体先输出 panic `0x6a`（106），无成功标记。队列自行推进不能冒充 IRQ 完成证据。 |
| 独立 RAM MMIO/ring | 64 个同时 outstanding heads；逆序完成；最大 descriptor 长度 65536，index/next 63，地址高低字节；拒绝越界长度/index/next/flags，拒绝重发/改写活跃 head。 |
| 失败不消费 | used.idx 超出 64 或超过已发布数、head=64、未发布 head、已完成 head 均 Invalid；原位置修正后成功，未丢失 consumed 或 outstanding 状态。 |
| 队列与机器边界 | 非对齐/重叠页面、queue_max=63、已 ready 队列均拒绝；64 成功。16 位与 8 位写入保留邻接字节，descriptor wire 字段及 notify queue number 检查通过。 |
| 原样 completion length | `0xffffffff` 原样交回调用者，明确不是 transport 的长度验证承诺。 |
| 独立语义负控 | 仅在构建快照删去 publish 的 duplicate-head guard，探针精确停在 assertion 25 (`00000019`)，无 PASS。证明探针能辨别重发错误。 |
| 宿主只读核验持久字节 | 两轮退出后打开实际 disk.raw，在偏移 68157440 对比全部 4096 字节，512 个 u64 均为 `0x123456789abcdef + i`；不只是首字标记。 |

独立 ring 探针采用真实生产 io/virtio 源码，但以固定保留 RAM 模拟设备寄存器和 used ring。它验证状态、边界和 wire access，**不能**证明真实设备内存排序或 IRQ；后者由实际 virtio-blk QEMU 正/负例提供。`boundaries-r1` 是同一探针首次通过记录；最终正式脚本增加负控选项后重跑为 `boundaries-r2`，本判定使用 r2。

## 源码核查与接口责任

- `io.s0` 的 byte/halfword/word/doubleword 指令与源码对应；访存前后使用完整 fence。C ABI 不修改 callee-saved 或 x27。S0 编译器将 `fence` 编码为保守 `iorw,iorw`，本次未修改编译器。
- queue 的 64 位 bitmap **只跟踪 head**，不证明 chain body 互斥。block 固定 0..2 链、input singleton 等具体驱动必须保持 body 与 buffer 所有权，直到设备完成。
- `take` 在读取 aligned used.idx 后通过 fenced access 读取条目，验证进度差和 live head；不验证设备写入长度。driver 必须检查 used.len、状态、预期请求和设备错误。
- `queue` 三页必须由调用者提供零化、互不重叠、固定存活的 DMA 页面，且身份映射地址确实是物理地址。地址存在性/页所有权并不由整数参数自动证明。
- `Queue` 值可复制，调用者必须保持唯一的权威状态；不能用陈旧副本继续操作同一实际 queue。生产约束为单 hart、串行 S-mode 操作；此通过不扩展到 SMP 或同一 queue 的并发访问。
- descriptor 内容准备完成后才发布，available.idx 使用单个对齐 halfword store，并在发布和 notify 前后有 fence；这里没有观察到 tearing BUG，不能将先前理论风险写成已复现故障。

## 限制与后续门槛

未发现此冻结范围内的阻断缺陷。没有覆盖生产保护页表中的 PLIC/MMIO 映射、真实 U-mode IRQ 上下文、DMA 分配及取消、设备超时/损坏后的生产清理、FS/正常关机收尾、K5 输入/ramfb；这些仍分别属于完整 K4/K5 验收。没有内核延迟或 5ms 目标的通过结论。FLUSH 与正常重启测试不构成突然断电事务恢复承诺。

本报告及 JSON 保存可恢复身份；原始输出在 ignored build 目录。新增独立测试位于 `tests/k4/independent_transport/`，不属于原候选生产文件，无生产改动、无提交。
