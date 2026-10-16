# C-r1：ABI常量与平台身份

作者/root，输入为已验收C-r3设计和规约。ABI1的编号/偏移以abi/contract.vt为唯一机器可读来源；具体外部布局与保留字节在README明确。没有生成宿主头文件、没有新增语言类型。系统调用号已分配，除exit外的请求参数/记录尚待对应K3/K4/K5冻结，不把预留编号称为已实现服务。

当前ABI探针使用维护版E3编译，在RV64 Linux-user实际执行；7种记录由VT按常量写出，读取独立Python oracle字节并逐字节比对，再由host比对输出；损坏sepc字节的负控退出12且不发布文件。另验6项几何关系。实际3条命令、输入/输出记录见build/k0-abi-r1/verification.json。只证明常量/字节布局，不证明完整BootInfo/FS验证器或内核usercopy。

平台清单记录本机QEMU system/user、Clang及OpenSBI完整SHA。GNU名义交叉as不可直接执行，初次查询出现Exec format error；随后file -L确认安装目标为空文件；采用本机Clang作独立机器编码oracle，不把它纳入正式镜像构建。

候选文件哈希见C-candidate-r1.json。保留旧设计正文及旧候选；README和新实施记录将单列当前状态，不能把旧“尚未实施”设计历史直接当现状。
