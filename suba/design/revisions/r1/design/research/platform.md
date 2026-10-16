# 平台与启动链调查（A 候选 r2）

日期：2026-10-13。需求输入：`../../REQUIREMENTS.md`。这是架构决策及证据，不是 suba 内核、驱动或自举已经实现的声明。

## 结论

首选固定 **QEMU virt / RV64 / TCG / 单核 / 512 MiB RAM / raw 磁盘（容量与槽布局由 C 冻结；调查以 1 GiB 稀疏临时盘实例化）**。图形使用 **ramfb**；存储、键盘、绝对坐标指针使用现代 virtio-mmio。内核处于 S-mode，应用处于 U-mode，Sv39 隔离；OpenSBI 是固定外部固件，提供 TIME 与 SRST。单独的固定 S-mode stage0 从磁盘原始启动区装载可重建内核 ELF，重启后仍读取磁盘的新产物。

ramfb 是正式选择：用户需要固定虚拟平台的窗口桌面，并未要求 GPU 协议、3D、动态分辨率或硬件加速。本机缺少 virtio-gpu 设备，但选择 ramfb 的主要理由是它把显示边界缩为一个帧缓冲及一次配置，免除 GPU 资源、队列和传输命令。真实内存管理、块设备与输入仍通过标准机制教学；未来 GPU 驱动可作为独立扩展。

## 本地证据与正式配置

[完整帮助输出](platform-local-help.json) 保存 8 条命令、返回码、stdout/stderr。本机 `qemu-system-riscv64` 为 **11.1.1**；`virtio-blk-device`、`virtio-keyboard-device`、`virtio-tablet-device`、`ramfb` 可用；显示后端为 none/gtk；`virtio-gpu-device` 查询失败，不能声称本机有 GPU 设备。

[初始实例化证据](platform-local-probe.json) 包含暂停状态 QMP `info qtree`，[DTB](platform-probe.dtb) 与 [可读 DTS](platform-probe.dts) 是无 ramfb 的第一轮探针。随后 [ramfb 探针](platform-ramfb-probe.py) 使用完整设备组合，结果在 [JSON](platform-ramfb-probe.json)：成功找到 `etc/ramfb`，通过 fw_cfg DMA 配置 64×32 XRGB8888，抓帧逐字节匹配红色；直接改变一个帧缓冲像素后，下一帧匹配绿色，无第二次配置或 GPU 提交。

该探针以 qtest 发出物理 MMIO/内存操作、以 QMP 验证显示输出，CPU 暂停。它验证了宿主设备模型及协议，不验证 guest 驱动、PLIC、GTK 实际输入、正常运行刷新时序或启动链。临时磁盘仅用于实例化，已经移除；JSON 保留原始命令中的临时路径，不意味着路径仍存在。运行 Python 探针会创建自己的临时文件，可复现。

候选运行命令（`stage0.elf` 尚未实现，不能直接当成可启动产品）：

```sh
qemu-system-riscv64 \
  -machine virt,aclint=off,aia=none,acpi=off,iommu-sys=off \
  -accel tcg -cpu rv64 -smp 1 -m 512M \
  -bios <固定且记录哈希的 opensbi-fw_dynamic.bin> \
  -kernel <固定 stage0.elf> \
  -global virtio-mmio.force-legacy=false \
  -drive file=suba.raw,format=raw,if=none,id=subadisk,cache=writeback \
  -device virtio-blk-device,drive=subadisk,bus=virtio-mmio-bus.0 \
  -device virtio-keyboard-device,bus=virtio-mmio-bus.2 \
  -device virtio-tablet-device,bus=virtio-mmio-bus.3 \
  -device ramfb -display gtk -serial stdio -monitor none
```

补充[入口/复位探针](platform-entry-probe.json)已实测：QEMU 默认 OpenSBI **v1.8.1**、运行时 SBI 3.0，进入 `0x80200000` S-mode；同一个 QEMU 进程经历 SRST cold reboot 后再次进入固定 ELF，先后输出 S0/S1，再 SRST shutdown 以状态 0 结束。探针只用保留 RAM 标记，不读磁盘，不能替代磁盘新内核验收。源码为 [汇编](platform-entry-probe.S) 与 [链接布局](platform-entry-probe.ld)，使用宿主 clang/lld 仅作调查。首次仅指定 `-Ttext` 导致 ELF 还有低地址 PT_LOAD，QEMU 报告 Next Address=0x10000 且未到入口；失败记录保留在 [r1](platform-entry-probe-failed-r1.json)。显式限定 PT_LOAD 后通过。正式 stage0 ELF 必须约束所有装载段和低地址，不可只看 e_entry 或文本地址。

CPU 与 QEMU 二进制/固件哈希必须纳入实现环境清单。调查使用 `-bios default`、`-display none`；正式版本应固定其解析到的固件，不随系统包更新漂移。`bus.1` 留空是现有探针事实，不是保留一个 GPU 的架构要求。机器仍会实例化 PCI bridge 等内建硬件，suba 不实现或依赖其驱动。无 `-snapshot`、`-no-reboot`，也不将可变内核传给 `-kernel`。

## 设备、发现与所有权

QEMU virt 提供 DTB，包含 RAM、MMIO、IRQ、CPU 与时钟信息；采用有界 FDT 读取器取得所需属性，再校验固定配置，不实现通用硬件枚举框架。QEMU 官方建议从 DTB 发现设备；本调查中的地址只属于已测机器配置。[QEMU virt 文档](https://www.qemu.org/docs/master/system/riscv/virt.html)

| 设备 | 本机配置值 | suba 责任 |
|---|---|---|
| RAM | `0x80000000..0xa0000000`，512 MiB | 排除固件、stage0、DTB、内核、启动栈、页表、DMA、帧缓冲，再分配给进程 |
| UART | `0x10000000`，PLIC IRQ 10 | 早期诊断/panic；8 位 MMIO，不作为最终桌面的替代 |
| PLIC | `0x0c000000` | 从 DTB 的 interrupts-extended 选 hart0 S-context；claim→设备确认→complete |
| CLINT / timebase | `0x02000000`；10 MHz | 内核通过 SBI TIME 编程时钟；不同时另写 CLINT/Sstc |
| virtio block | bus.0，`0x10001000`，IRQ 1 | 一个 split queue、读写与 FLUSH；阶段0轮询，内核运行期中断推进 |
| virtio keyboard | bus.2，`0x10003000`，IRQ 3 | 一个事件队列，键状态转换；不把 evdev 编码等同 UTF-8 字符 |
| virtio tablet | bus.3，`0x10004000`，IRQ 4 | 查询绝对坐标范围，映射到固定屏幕并交付按钮事件 |
| fw_cfg | `0x10100000` | 发现 `etc/ramfb` 并配置；只由可信显示初始化代码使用 |

块设备/输入 transport 校验 Magic、Version=2、DeviceID、队列上限和 FEATURES_OK。仅协商实际实现的功能：VERSION_1，block 额外要求 FLUSH；不协商 packed ring、indirect descriptor、event index、IOMMU、multiqueue。固定小队列也必须先读 QueueNumMax；容量不足启动失败。所有 virtqueue 地址为 guest **物理地址**，不能填写用户虚拟地址。DMA buffer、descriptor 和请求状态归内核，用户退出不直接释放设备仍在访问的页。使用提交前/完成后内存屏障及 MMIO 顺序；单核不免除此要求。输入缓冲始终及时补充，按 SYN_REPORT 形成输入批次，不能依赖应用回补硬件队列。[Virtio 1.2，§2.7、§3、§4.2、§5.2、§5.8](https://docs.oasis-open.org/virtio/virtio/v1.2/virtio-v1.2.html)

取消应用等待只是取消交付，不会神奇撤销 DMA：未完成 I/O 必须由系统继续收尾，再释放其内核缓冲与请求。对固定可信设备，无完成超时作为平台/驱动故障进入 panic；不在一个长期关中断忙循环里等待。stage0 尚无进程，可以有界轮询并在错误时停机。

Sv39 的 U/PTE 权限、SUM 默认关闭、不可执行数据和栈、切换地址空间后的 sfence.vma、进入新代码前 fence.i 属于内核/机器层合同。应用不映射 MMIO、固件、其他进程或硬件 DMA 队列。[RISC-V Supervisor ISA](https://docs.riscv.org/reference/isa/v20260120/priv/supervisor.html)

## ramfb 的实际成本与边界

初始化从 fw_cfg 文件目录按名字查找 `etc/ramfb`。配置结构为 28 字节：物理地址 u64，fourcc/flags/width/height/stride 各 u32，所有字段大端。选择 **1024×768、XRGB8888、stride=4096、flags=0**；前缓冲为 **3 MiB 连续物理 RAM**，终身由显示系统拥有，绝不交给普通应用。little-endian 像素内存为 B,G,R,X。驱动配置一次，软件合成器把完成区域复制到前缓冲；宿主读取同一 RAM。QEMU 的 ramfb 实现映射来宾内存并更新显示面，不要求 guest GPU transfer/flush。[QEMU ramfb 实现](https://github.com/qemu/qemu/blob/master/hw/display/ramfb.c)

fw_cfg 的 MMIO selector、DMA 地址及 DMA 描述符使用大端，目录 size/selector 也使用大端；数据寄存器按字节读取。DMA 完成必须检查控制字段归零、错误位和有界超时；不能使用已取消支持的数据端口写入代替 DMA。配置缓冲、DMA 描述符在完成前保持有效。[fw_cfg 官方协议](https://www.qemu.org/docs/master/specs/fw_cfg.html)

系统保留一个软件合成缓冲（另 3 MiB，虚拟连续即可）及应用窗口表面；前缓冲的直接写权限只授予最终选定的可信合成器/内核通路。这里不是让普通应用直接绘制桌面。固定模式无需显示中断、PCI、GPU 资源/命令协议、光标设备或动态分辨率框架。接受撕裂和宿主刷新节奏，不承诺 vsync、原子翻页或显示完成通知。鼠标指针也由软件合成。[ramfb standalone 更新入口](https://github.com/qemu/qemu/blob/master/hw/display/ramfb-standalone.c)

以上内存数字为显式设计选择；它们不证明整个桌面/编译器在 512 MiB 下的峰值已经测过。内核启动时需一次预留帧缓冲，避免后期因物理碎片无法取得连续区域。

## 固定启动基础与可重建边界

比较：

| 路线 | 获得什么 | 新增责任 | 判断 |
|---|---|---|---|
| OpenSBI + 自有 S-mode stage0 | 已有特权初始化、SBI时钟/复位；自行解释磁盘内核 | 一个小型块读取器、限定 ELF 装载器 | 首选；外部固件单独计账 |
| 自有 M-mode shim + stage0 | 固件主体可自研 | PMP、异常委派、M陷入、timer转发、SBI子集、reset均需实现验证 | 当前不选；不是“几条 mret”即可完成 |
| OpenSBI + U-Boot/UEFI | 现成磁盘/文件系统/启动管理 | 庞大外部启动生态及格式约定 | 对固定教学系统超过需要 |
| 每轮宿主 `-kernel new.elf` | 最快单次演示 | 内核更新仍依赖宿主重装 | 不满足完整闭环 |

首选链路：QEMU reset ROM → 固定 OpenSBI → 固定 stage0 → 磁盘启动区的新内核 ELF → 内核挂载自身 FS 并启动桌面/工具。FW_DYNAMIC 由前阶段传入下一阶段地址等信息；OpenSBI 自己不是磁盘加载器。[OpenSBI FW_DYNAMIC](https://github.com/riscv-software-src/opensbi/blob/master/docs/firmware/fw_dynamic.md)

边界必须写明：

- **不可变外部基础**：QEMU/ROM/OpenSBI，以及项目提供且源码可读的 stage0 种子。它们不属于首版系统内必须重建范围。stage0 是单独计账的自研引导代码，不伪装为 QEMU 自带能力。
- **可重建部分**：S-next 编译器、内核的 S-next 与所有必要入口/trap/机器操作汇编、运行库、驱动、文件系统、桌面、编辑器、应用、原生构建和启动发布工具。它们不能依赖 stage0 帮忙实现内核运行机制。
- 初次宿主构建/放置 stage0、固件、种子系统磁盘之后，正常内核更新只写虚拟磁盘；宿主启动命令和固定文件不变。不能将重新启动 QEMU 且替换 `-kernel` 路径作为验收。
- stage0 以 S-mode、satp=0、关闭 S 中断开始，建立自己的栈；固定保留它与固件占用区域。建议 stage0 装载 `0x80200000`，内核物理入口 `0x80400000`，二者不得相互覆盖；最终边界由 C 节点内存合同冻结。DTB 必须在跳转前复制/保留，并把地址、长度、RAM保留区等作为 BootInfo 交给内核。
- stage0 只认识固定启动区头和限制后的 ELF64 LE/RISC-V PT_LOAD，不挂载正式文件系统。所有文件偏移、加法、filesz≤memsz、目标RAM、保留区、不重叠与入口范围先验证后写；BSS 清零，关闭/reset 其块设备队列、fence.i，再跳入内核。内核重新初始化设备，不继承 stage0 的请求、指针或队列。

启动发布工具在 suba 内读取内核 ELF、完成与 stage0 同样的结构验证，把它写入磁盘保留 extent，再 FLUSH，最后写启动头/长度/校验值并 FLUSH，成功才允许显示“已发布”。启动区与文件系统空间分配永不重叠；用户应用无原始块写接口。槽数、选择记录与回退规则由 C 节点冻结。可选择双槽以保留上一版便于调试，但这不增加掉电原子发布承诺。C 当前候选为 256 MiB 整盘：1 MiB 启动元数据、两个 32 MiB 装载槽、191 MiB 文件系统；槽约束文件字节数，ELF 的内存跨度另行验证，不能混淆文件大小与 BSS/地址间隙。未确定发布成功时禁止正常重启并显示诊断；结构/校验不合法由 stage0 按 C 的回退合同处理，无可用槽则串口停机。

正常重启先拒绝新构建/文件修改，结束或收尾 I/O、文件系统写回与块设备 FLUSH，停用显示/输入推进，再调用 SBI SRST cold reboot。SBI 规定成功不返回，失败需报告；TIME 以绝对时刻编程下一次 timer。二者启动时查询支持，缺失即不满足正式平台。[SBI SRST](https://github.com/riscv-non-isa/riscv-sbi-doc/blob/master/src/ext-sys-reset.adoc)、[SBI TIME](https://docs.riscv.org/reference/sbi/ext-time.html)

**部分已测、关键磁盘链仍未测**：QEMU reset 后固定固件/后继 ELF 重新执行已由上述入口探针证明；新磁盘内核的 FLUSH、再次读取、装载仍未实测。设备实例化或现有 P5 monitor 不能证明完整链路。实现 P0 必须实测两次内核标记切换，宿主进程与命令不变；失败必须修正启动路线，不能悄悄以 host reload 通过验收。

## 进入实现的最小探针与门槛

1. **启动/复位**：最小 stage0 读固定磁盘标记与限格式 ELF；来宾更改磁盘标记并 FLUSH→SRST→再读到新标记；串口记录 OpenSBI版本、stage0哈希、内核标记。正式 stage0 不可变，变的是磁盘产物。也测试错误长度/保留区覆盖/校验失败。
2. **保护/抢占**：S/U、Sv39、SBI TIME、PLIC 入/退中断；U-mode 死循环可抢占，非法写内核页仅终止对应进程。验证 trap 栈及 sp 切换，不以 M-mode P5 测试代替。
3. **块设备等待**：现代 transport 协商、读写 FLUSH、实际 IRQ 完成；发起进程退出后 I/O 能收尾且页不提前复用；写满/错误/重启持久化有受控结果。
4. **显示输入**：将已实测 qtest 序列实现为 guest 驱动，在 GTK 中显示 1024×768、键盘和指针事件正确；编译/死循环背景下桌面仍响应。验证 ramfb reset 后重新配置和帧缓冲保留。
5. **容量**：运行实际移植编译器（当前已有约 55 MiB RW 预留）与桌面，记账内核页、页表、帧缓冲、窗口、文件缓存、输出、用户栈和峰值；512 MiB 是可调整的初始工程配置，不是已证明最低配置。

这些是有界可行性探针；产品驱动/内核实现仍需在同一接口与生命周期合同下集成。UART/OpenSBI/S-mode 后继/正常复位已通过有界探针；块/input IRQ、guest ramfb、GTK、磁盘更新→重启尚未在本调查中通过，不把架构接受写成运行接受。
