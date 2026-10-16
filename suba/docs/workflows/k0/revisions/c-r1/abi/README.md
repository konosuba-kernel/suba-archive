# suba 序列化 ABI 1

[contract.vt](contract.vt) 是编号和布局的权威源，普通 S-next 常量可由 kernel/user/格式工具直接 import；不是由宿主生成的头文件。所有记录小端，显式读写，不能按 VT 结构布局强转。这里冻结跨阶段边界，不表示系统调用或文件系统已经实现。

BootInfo 固定512字节：magic/u64；version、length/u32；RAM、DTB、kernel地址与长度/u64；slot、crc32、reservation_count/u32；128起最多16对 `{base:u64,bytes:u64}`。保留字段为零，保留范围须在RAM内、非零且无溢出；DTB必须落在登记保留范围内。kernel范围为实际已装载跨度。slot仅0或1。BootInfo由stage0持有，kernel验证后复制所需事实。

TrapFrame的xN偏移为`(N-1)*8`，1≤N≤31；其后为sepc、sstatus、scause、stval；内容280字节，分配288字节。只由内核机器层持有。恢复sstatus必须按保护合同筛选，不能从用户记录直接恢复。

启动参数页4096字节，magic/u64；8起version、length、argc/u32；20保留；24/32为stdout/stderr句柄/u64；40/44为cwd的offset/length/u32；48为数据区已用字节数/u32；52..64保留。64起64对argv offset/length/u32；数据从576起，cwd及每项argv必须完整落在已用数据区，无NUL、为有效UTF-8，不需要尾零。未用argv项及页余量为零。参数页由loader建立为只读，入口a0及x27指向它；不使用Linux初始栈。

句柄0无效。低8位是slot+1（1..64），高56位是非零代数；代数耗尽则退役，不回绕。令牌的数值不代替调用者、类型、rights检查。

系统调用号固定在contract中；a7选择操作，a0..a5输入，a0返回状态/a1返回值。SYS_EXIT的a0是u32退出码且不返回。其余操作的记录字段和参数签名在对应K3/K4/K5实现前另行冻结；在此之前调用号是保留分配，不构成可调用服务。未知或未实现操作必须Unsupported，不得假成功。修改已冻结字段/号需提升ABI版本。

窗口事件64字节：version/length/kind/flags为u32，window/sequence为u64，payload从32开始。Key载荷为code/u32、pressed/u32、modifiers/u32；Pointer为x/y/buttons/u32（绝对非负坐标）；Focus为focused/u32；CloseRequested无载荷；Overflow为lost/u64、当前buttons/modifiers/u32。未用载荷为零。队列序号不得回绕复用；恢复键状态按窗口生命周期合同处理。

启动头4096字节：magic/u64；version/length/active/header_crc32为u32；32起两条16字节槽记录，valid/length/crc32/reserved均u32。valid只有0/1；无效槽必须全零。头CRC32覆盖整个头、计算时将header_crc32四字节视为零；槽CRC覆盖精确ELF文件长度。CRC32采用标准反射IEEE多项式0xedb88320，初值/末异或均0xffffffff。其余保留字节必须零。槽固定offset/size，禁止信任磁盘提供任意地址；头active仅0/1。正式loader必须读完整头/文件和验证全部段后才能装载。

FS superblock4096字节：magic/u64，其余列出的字段均u32；48之后保留为零；CRC算法同启动头。root编号1；节点引用1..4096，0为无引用；节点i在节点区`(i-1)*128`。空节点全零但generation可保留以防复用；generation/u64，parent/name_length/u32，file_bytes/u64，first/last/u32，其余kind/flags/u32。name最多63字节UTF-8且无NUL和`/`，未用字节为零；103..128保留为零。root为Directory、parent=0、空name；目录size/first/last为0，文件空数据链first/last为0。flags初版磁盘值必须0（运行时seal/Frozen/引用不写入磁盘）。FAT索引是分区相对块号；metadata和尾部超出FS_BLOCKS的FAT项为Reserved。挂载验证链归属/环/容量属于K4。

实际消费者和双向字节探针必须覆盖这些常量，汇编需要的寄存器/现场偏移应由S-next构建工具读取这些常量生成或按固定公式计算，不维持第二份手写偏移表。
