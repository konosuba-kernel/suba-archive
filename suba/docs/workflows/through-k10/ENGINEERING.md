# 实施中的阻塞与发现

## K8：原生固定点预演

K7 尚未验收，`build/k8-native-explore-r1` 只是提前探索。生产 kernel/seed 均来自
K7-r2 冻结输入，控制器只使用正常 FS/Child/Stream API。第一代生成约 306 秒，
退出后的页/流回到基线；后续代际、完整字节与行为扰动仍需完成，不提前声明自举。

## K9：RAM 引导隐藏的宿主编译依赖

旧 `kernel_probe.py` 为每个内核生成 `config.vt`（入口/末地址），再编译测试 boot。
若用这个动作部署 guest 内核，会违反“宿主仅搬运”的边界。准备固定的 `boot/ram.vt`：
启动时验证 launch descriptor 的有界 RAM 范围、解析原始 ELF、构建 BootInfo；
后续 `ram_launch.py` 只验证哈希/范围并按字节复制，不调用编译器或链接器。
这是依赖完成前的探索，须在 K9 验证坏 ELF、搬运损坏及不同 kernel/S0 产物。

最初用通用 `build_users.build` 试编 boot 返回 `E_NAME file=0 byte=0`，原因是该工具
只生成用户清单形状，没有 boot 必需的 `bind panic`；改用完整 `boot/ram.build`。
这是测试构造错误，原始编译日志保留，不计作语言编译失败。

## K10：尚缺真实正常关机

生产已有 SYS_POWER 编号、FS shutdown_step 和 SBI power_off，但没有连成生产路径。
不得用 host terminate 替代 guest 正常关机；关机涉及新请求拒绝、普通应用结束、
DMA/临时对象排空和最后 FLUSH。完整盘点见 K10-inventory.md，正式实施在 K9 后。

K9 引导预演 `build/k9-ram-explore-r1` 已在 2.74 秒通过同盘 remount 控制器；
固定 boot SHA 与装载的 kernel/user/disk 身份见 deployment.json。
`k9-transport-explore-r1` 拒绝五类旧身份/损坏/地址/容量输入，拒绝发生在建立部署目录之前。
`k10-platform-explore-r1` 在真实 QEMU 中分别缺 block/keyboard/tablet/ramfb、使用 legacy transport、
以及 256MiB 错误 RAM 配置，六例均由 guest 受控拒绝；不是宿主 QEMU 参数错误退出。
以上均是旧内核上的探索，尚未形成当前 K9/K10 判定。

K8 预演首轮 C0/C1/C2/C3 全文件均为 SHA256
`872580a5751997a32c7b91c127987117e375a866fa99ecb36292ab443d0bb63c`，
C3 也成功编译并运行返回41的应用。然而源码扰动步骤返回测试错误9：测试将临时文件写到
`/work/main.tmp`，再跨目录 replace 到 `/work/biomiya/compiler/main.vt`，违反现有“同父目录替换”合同。
原文件未损坏；失败盘和 partial-evidence.json 保留，整个首轮仍不通过。
修正测试将临时文件放在目标同目录；K9 测试中的相同问题同步修正。生产 FS 不放宽合同。

同目录替换修正的定向探索 `build/k8-mutation-explore-r1` 已在 guest 完成：
使用前一轮真实产生的 C3，正常无参数退出2 → guest修改main.vt → 原生编译mutant → 退出7。
每步退出原因正常，页/流/打开文件/FS请求账本恢复；第395秒到达绿色结果。
该定向实验不能替代随后正式K8的完整固定点+扰动同轮验证。

定向扰动的 Linux 同输入完整 ELF 对照也通过（verification.json passed=true），仍仅为探索。

## 工具与语言反馈：显式枚举分支、import位置

K9 Ctrl+M 清单选择的隔离UI预演最初使用枚举 `match` 的 `_` 分支，被当前 S-next 以
`E_TYPE file=25 byte=8583` 拒绝；改为显式穷尽的 Prompt::None/File/Manifest 和单一标签函数。
这是新测试/实现未遵守现有语言，不是更改语言承诺的理由。K10 计时插桩最初把 import 追加
在函数之后，编译器以 E_PARSE 拒绝；改为插在 module 后。失败快照保留，未更改生产源码。
这些错误的 file/byte 定位可用，但缺少“枚举不能用通配分支”“import必须先于声明”等具体解释，
可以作为后续诊断质量改进输入。

## GUI证据不能匹配旧画面

UTF-8 GUI探索r1真实展示并编辑了中文/四字节缺字/组合字符，保存及同盘重启字节验证成功。
但连续两次“打开失败”使用同一提示，第二次观察在0.03s内匹配旧画面，不能证明超限文件那次
输入已被处理。该分支不作为正式证据；工具已加每次新Open提示与Escape确认的状态转换，
正式K10会新跑。原始截图/时间保留，不用最后字节正确掩盖动作覆盖缺口。

计时插桩第二次编译因 entry↔dispatch import 环被 E_NAME 拒绝。观察状态移入dispatch，entry
沿既有依赖调用，未给生产增加反向依赖。第三次kernel成功，但desktop测试缺import（模块名
误写为带函数main的路径）失败；保持原报告并把确实编译成功的kernel作为显式缓存，修正用户
快照后复用。计时测试的源码/目标身份均单列，不与正式生产二进制混淆。

## K8候选清单边界

K8-r1冻结脚本递归收集.vt/.s0/.build时，误把host oracle与导出目录的派生文件也列作初始编译输入。
独立review指出oracle/main.vt在行为对照阶段本来就要改为guest读回的源码。保留r1，r2改为从实际
kernel/user0/boot三个清单枚举81项；源码、工具和guest初始输入没有改变，不重跑相同长计算。
派生产物和初始输入必须分开冻结，不能把通配扫描的结果当成依赖合同。

计时预演r4没有先给窗口焦点，F6仅到桌面而不到编辑器；r5改为等待focused又未注入点击，
因此等待条件永不满足。两轮主动结束并保留失败报告，不记为应用输入丢失。r6先观察两编辑器
首帧完成，再通过真实QMP鼠标点击取焦点，然后开始两个编译任务及100次输入测量。

K9 独立预审发现 host 搬运竞态：最初校验 expected，复制后仅比较 source与copy，
允许两次检查间被修改的源成为新有效副本。已改为复制前固定所有输入哈希，副本必须匹配固定
身份；异常不产生 deployment.json。可控 copy-hook 测试覆盖此竞态；不修改guest产物或ELF。

正式K9首轮 build/k9-native-r1 在第45秒返回freeze inputs Busy。复用K8 command助手时，
先spawn构建器再CREATE_NEW日志，可能在Job捕获epoch之后修改工作区。日志创建移到spawn之前；
正常构建器只在freeze之后输出，因此其后日志写入不影响本轮快照。K8原证据仍绑定当时助手哈希，
不改旧候选；该两行顺序调整作为K9测试修复由reviewer复核。
