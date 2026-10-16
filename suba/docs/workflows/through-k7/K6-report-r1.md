# K6-r1 文本、字体与编辑核心候选

2026-10-15，作者 `/root/ram_fdt`。前置 suba `7712dd3` 和 K0 冻结编译器，待 root 独立验收；没有自行提交，也没有声明 K7 的系统内 UI/保存已完成。

## 交付

- `user/text/utf8.vt`：严格 Unicode scalar 解码与边界，支持1–4字节，拒绝 overlong、surrogate、截断和超界。无归一化或丢弃字节。
- `user/edit/{buffer,motion}.vt`：单一所有者的有界 gap buffer，最多4MiB；选择、插入/替换、完整scalar删除、左右/行首尾/上下移动、进程内复制、snapshot、readonly spans、rehome。失败保留内容/cursor/anchor/version，版本不回绕。
- `user/text/font.vt`：不可变资源验证、BMP直接索引、8/16×16字形读取和像素查询，缺字16×16方框。
- `tools/fontpack/`：可重用纯S-next转换核心，以及已经实际执行的Linux适配；字体产物不是Python生成。K3适配可换I/O，不需要重写转换算法。
- `assets/unifont/`：实际官方GNU Unifont17.0.04源、原生工具生成的完整字体、精确覆盖表、完整许可/版权/作者说明、下载与产物哈希。57086个BMP字形，包含基本汉字和扩展A全段；不承诺补充平面字体。选择OFL1.1分发字体，来源资料保留双许可原文。

可直接供 K7 使用的接口和所有权前置条件在 `user/edit/README.md`、`user/text/README.md`；格式/覆盖/重建在 `assets/unifont/README.md`。没有改 ABI、内核、编译器或全局设计。

## 真实检查

复现入口：

```sh
python3 tools/check_k6.py --compiler ../biomiya/build/layout-p4-r1/e3.elf --out build/k6-review
```

最新作者运行 `build/k6-r4/verification.json`：**348项通过**，包括24组各100步的Unicode字符串模型对照、精确4MiB文档、容量/别名/版本耗尽、gap两侧解码、反向选择、全字体原生转换/确定性/逐字节oracle和生产pixel输出。每步编辑均比较内容、cursor、anchor和version；模型用Python字符串切片，没有复制gap算法。

两项负控均要求实际得到明确错误语义而正常返回：放过overlong得到错误scalar；容量失败破坏anchor得到错误状态。没有拿异常/超时当作负控成功。另有仅测试副本的版本上限2，用于验证耗尽前后行为。原始测试输出与源码副本保留在build；版本化摘要仅引用路径和SHA256，避免复制大量逐例JSON。

公开scalar、字体与编辑失败分支都由真实S-next代码执行。原生fontpack对完整3762996B源转换两次，均产出同一2162704B字体，与官方每个glyph的独立wire预期完全一致。13个字形通过生产glyph/pixel读回并核对每像素。作者还查看了这些生产像素的宿主放大预览（build/k6-r3/glyph-preview.png），中文及缺字方框正确；这不是suba窗口集成证据。

## 成本与状态责任

生产文本/字体/编辑库共 **486行VT**，没有可变static。原生fontpack含适配共 **149行VT + 8行S0**；全部手写生产合计 **643行**。字体源和数据另计：源hex3762996B，packed字体2162704B，gzip溯源副本936643B；实际文件字节以K6-cost为准。

编辑库最长实际调用链5920B，最大单函数frame2320B；fontpack纯转换链5136B，最大单函数frame2480B。每个frame来自本次ELF机器码前导，不是源码局部变量估算。详细函数/frame与调用图在原始verification.json；compact成本表记录入口、ELF段和原记录身份。测试缓冲BSS、字体和fontpack适配输入/输出存储均独立列账。4MiB文本storage由调用者提供；核心没有藏匿分配器。

Document私有字段，所有操作unsafe以显式要求活跃独占backing和串行调用。S-next允许值复制，因此副本只是别名。spans/Glyph不延长底层存储生命；编辑spans在下一次移动或修改后失效；rehome成功后旧backing不再被Document引用，外层确认没有借用后可释放。测试通过迁移后覆盖旧存储证明Document已转到新backing，不能将此解释为语言静态借用检查。

gap恒在cursor，选择的一个端点因此恒在gap边界；正向选择读prefix，反向选择读suffix，snapshot组合两侧。不存在“移动gap而保留一个跨gap原始切片”的API。

## 明确留给 K7

FS读写、保存临时文件/sync/replace、窗口键鼠、像素裁剪/布局、保存版本与旧诊断提示、build作业均由K7集成。核心只保证snapshot无损和版本可核验，不把Linux stdout写入当作suba持久保存。

编辑粒度是scalar，不是grapheme；上下按scalar列，不是像素列，无sticky column或undo。所有同步复制/移动最多4MiB，运行于可抢占用户进程，不用于IRQ或不可抢占内核片。中文输入来自文件/粘贴/源码字符串，没有IME。单字体、单字形，无塑形/双向排版/归一化，字体不覆盖的四字节scalar仍原样保存。
