# R-r1 独立验收：Accepted

验收者 `/root`，未参与七份修订文档编写。候选 SHA256 `f58658cb7b97dea87209fc7640f0912fbe26da1224d9ffa6ebf650d955e3bc49`；九个候选文件逐项哈希匹配，本地链接再次检查无缺失。

对照用户最新授权逐项阅读 REQUIREMENTS、ARCHITECTURE §5/§8、CONTRACTS 发布/关机/构建合同、IMPLEMENTATION DAG/验收表和 SCOPE_REVISION：原生应用、编译器固定点、kernel及必要S0完整ELF为必需；host仅按字节搬运且guest/副本/实际装载身份相同；同输入host构建仅作为独立oracle，不替代guest产物。磁盘stage0/槽发布/回退/stage0原生检查延期。K4只依赖运行期K3，唯一拥有底层传输，延期K1消费其已冻结接口，DAG无环且未丢失必要驱动所有者。

普通文件正常sync/FLUSH/关机后读取、抢占隔离及完整回收、桌面/UTF-8/中文字形、编译器原生扰动与固定点均保留。当前ABI编号和槽布局保留而非首版实现承诺。CODE_STYLE仅两段状态/链接纠正，unsafe/错误/生命周期规约强度不变。K2a局部完成不解除整个K2/K3门槛。

这次接受的是范围修订，不证明尚未实现的机制。旧C-r3/K0历史文档哈希已显式失效于当前文本，历史实现/机器证据未被重写。可以正式启动M物理页节点；本轮使用调用者独占捐出的RAM extent（kernel专属BSS arena），不把窄BootInfo当作全RAM保留区验证。
