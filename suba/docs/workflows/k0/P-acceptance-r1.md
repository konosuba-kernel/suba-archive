# P-r1 独立验收

2026-10-14，验收者/root。**Accepted**，范围为固定profile/桥/入口及H接口接入，不能代替完整系统集成。

候选15文件SHA全部匹配P-candidate-r1.json。源审查确认高地址text/data/ABS64/PCrelative共用target布局，相对偏移对齐不把高地址传入64MiB范围helper；boot/kernel入口必须段首，BSS边界为匿名linker符号；栈计入RW/window，机器入口无旧sp依赖且保留a0/a1；panic/返回与user退出明确分离。bind验证数量、角色、普通安全函数及具体标量签名；trap尾桥保留ra。保留原Linux生成路径。

独立执行 `python3 -O core-s/tools/check_q_profiles.py --compiler core-s/build/k0-p/compiler.elf --baseline core-s/build/behavior-fixes-p4-r1/e3.elf --record-dir core-s/build/k0-profiles-root-r1`，26场景通过。实际QEMU启动boot/kernel，污染BSS仍通过，读已重定位静态切片与x27/sp/SIE检查通过；trap尾桥返回124、checked panic走101、函数正常返回走102。Linux样例与维护E3全文件一致。签名、缺失/重复桥、超窗口、错误段首等反例被拒绝。记录为P-root-r1.json。

H当前冻结接口与P使用字节一致，root已独立接受H。临时compiler仅为组件运行材料；精确整树源胶囊、Linux固定点及所有消费者由I另验。suba-user此节点只做布局/链接检查，尚未建立用户装载器/真实系统调用。128KiB栈无guard和紧急panic栈，不能声称K2已完成。
