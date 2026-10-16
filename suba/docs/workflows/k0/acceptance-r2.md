# I-r2 / A 独立验收：Accepted

验收者 `/root/k0_acceptance`，未参与 P/S/H/I 实施。接受对象为 `I-candidate-r2.json`，SHA256 `d0c6a1ad2872ba0aea0fa5603e3aef0027632ce63e1b3fc37da705b7b64701f9`，443文件。本结论接受 K0 工具链/ABI/固定平台边界和第一条正式 S-mode RAM 交接；不是整个 suba 系统完成。

## r1 阻断已消除

观察器现在持续收集500ms窗口，再以多个错误类别和终态序列共同判定。实际场景必须只有一条boot进入记录、其后恰好一个允许终态；普通panic、紧急异常、成功之间不能混合，重复或倒序不能通过。可信异常要求完整的scause=2、sepc、stval行。源码审查确认最终尾输出也参与判定。

独立执行：

```sh
python3 tools/check_kernel_entry.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/k0-acceptance-final-entry-r2
python3 tools/check_kernel_observer.py --record build/k0-acceptance-final-observer-r2.json
```

四个真实QEMU场景符合预期：正常交接、坏magic拒绝、可信异常三条路径成功；成功标记后插入非法指令的第四条负控实际先输出成功，再输出scause=2紧急异常，观察器正确返回失败（场景因正确拒绝而通过）。另有4个真实进程观察和20个终态序列检查通过。将r1独立产生的真实错误串口再次交给当前判定器，也得到拒绝。没有把“期望失败的场景通过”误写成异常路径正常通过。

完整独立命令/构建/运行记录、负控尾日志及哈希见 [evidence](acceptance-r2-evidence.json)，原记录副本为 `acceptance-r2-run-1.json`、`acceptance-r2-run-2.json`。r1的Rejected、旧候选及真实反例保留，不被本次覆盖。

## 冻结身份与结论继承

443文件、四份规范输入全部匹配；相较r1仅5个既有文件改变，所有旧字节存档与r1哈希相符。生产编译器、内核VT/S0、ABI、平台文件没有变化。23份结果原件与副本哈希、新失败尝试记录、成本每文件字节/物理行及总和均核对一致。最终复查候选没有漂移。[身份](acceptance-r2-identity.json) · [证据与成本](acceptance-r2-evidence-check.json)

`biomiya/tools/check_next.py` 的唯一并发改动是删除第64行的一个行尾空格；独立逐字diff和AST对比均确认，无语义或输入集合变化。因此已有P3/P4行为结论可以继承，但旧运行仍使用旧工具哈希，未冒称新工具曾完整执行。本变更不影响生产源或生成ELF，不要求机械重跑整条自举。

继承r1已核验的迁移影响、P/S/H/C独立接受、435既有场景和196项profile/S0/host专项结果；E1=E2=E3当前文件仍为 `049c6e094ccd044fba3b5d357583013b77f0e8e9a98d431ad919e02b0cda2144`，源码胶囊匹配、源码扰动真实行为与71冻结输入均沿用r1独立核查。本轮重跑专门覆盖观察器修复，不将未重跑的自举/既有回归记为新执行。

成本生产项未变：Q生产11307行VT、runtime375行VT+19行S0；kernel152行VT+111行S0；ABI199行另列。新增观察器检查使suba验证工具成为344行；它们不计作内核生产代码。未发现未解决的阻断。

## 接受范围与后续缺项

四固定profile、有限桥、独立S0编码、host边界、ABI常量与实际fw_cfg半字写均有相应证据。RAM boot fixture由QEMU预加载独立kernel；早期内核只接收窄BootInfo、输出诊断并进入无返回机器路径。500ms观察结合源码提供本阶段有限行为证据，不证明无限期稳定。

K1磁盘stage0/完整BootInfo与FDT校验/正常发布重启、K2页表与用户抢占回收、K3真实suba宿主服务，以及系统内编译器/内核自构建、FS和桌面仍未实现。本次接受不替代这些阶段的独立验收。
