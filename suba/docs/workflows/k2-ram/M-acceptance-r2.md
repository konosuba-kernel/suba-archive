# M-r2 独立验收：通过

2026-10-15，验收者 `/root`，未参与 M 的实现/测试。候选 SHA256 `a7c47872e619f3179b0ad5c89eabcd345cfac80293af30202de49ef4dbaa1e99`；12项文件与全部依赖哈希实查一致。M-r1 的生产/测试/报告字节未变；r2仅修正已接受D-r3身份，F枚举改名不影响M语义。

独立命令 `python3 tools/check_memory.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/k2-ram-m-independent-r1`，12/12通过，完整记录 M-independent-r1.json。检查高偏移测试确实使用最高slot=131071而managed=3，前导span大部分无实际映射；探针初始化后销毁原列表，仍能分配正确三页。内部洞/外围所有字节哨兵保持，释放最高页再用、stale token及其他存活页内容验证均真实执行。把valid边界改COUNT的副本实际退出20，不能以成功标记掩盖错误。

源码证明：regions_valid的previous_end从origin开始，先拒绝base<previous_end，再做base-origin减法；offset<=span后才减span-offset，span已经通过地址加法和最大页数校验。因此每段end、slot end和count不会溢出。所有描述符完整验证后才触碰SLOTS；只初始化列出的slots，并以tail连接跨洞free list，span中的洞从未转为地址或访问。私有Frame无法通过正常接口获得未捐赠槽，valid同时检查SPAN_PAGES与allocated/代数；COUNT仅表示捐赠总数。原release/clear/代数退役保持，运行期元数据O(1)，一次分配清512字。

额外静态检查覆盖失败后的状态和列表借用：READY为成功最后写入，只允许一次安装；本地Region视图没有保存到全局。所有全局状态独占于memory模块，unsafe要求序列化与释放前外部访问终结，没有虚构并发/映射保护。

成本与基线diff一致：新增51行，Slot仍12B，唯一新增永久状态SPAN_PAGES为8B；最小探针RW1572921B、单帧1456B。较大59312B frame来自测试栈backing，不是生产内核。I必须另验真实物理RAM与保留范围；此判定不含FDT、页表或隔离。
