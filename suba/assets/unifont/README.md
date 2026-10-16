# suba BMP 17 字体资源

实际来源是 [GNU Unifont 17.0.04 官方版本](https://unifoundry.com/pub/unifont/unifont-17.0.04/)，不是手写少数字模。上游 `.hex.gz` 解压为原样 `.hex`；从同版本完整源包取得许可、作者说明和 COPYRIGHT。源包中 `font/precompiled/unifont-17.0.04.hex` 与单独下载后解压的源完全一致。URL、获取日期、SHA256 和许可来源见 `provenance.json`。

字体源和转换后的 `suba-bmp.fnt` 按 **SIL Open Font License 1.1** 分发；保留上游双许可说明 `COPYING`、完整 `OFL-1.1.txt`、`COPYRIGHT` 和 `UPSTREAM-README`。本项目选择 OFL 许可分支，格式转换后的显示名称为 **suba BMP 17**。这些许可适用于字体资源，不把系统手写源代码视为字体来源程序。原生转换器是本项目的 S-next 实现，没有复制上游 C/Perl 工具。

共有 **57086** 个 BMP 字形，每字高 16 像素，宽 8 或 16 像素；包含完整基本汉字 U+4E00–U+9FFF 和扩展 A U+3400–U+4DBF。`coverage.json` 的闭区间表是精确覆盖，`.hex` 的每行给出完整逐字形数据。无字形 scalar（包括全部补充平面）显示 16×16 方框，文本原始 UTF-8 不变。组合字符独立显示，无字簇合并、双向排版、字体塑形或中文输入法。

## 从原始字体重建

从 suba 根目录执行（编译器拒绝覆盖既有 ELF，先选择新的 output 路径或移走之前生成的工具）：

```sh
qemu-riscv64 -s 1048576 ../biomiya/build/layout-p4-r1/e3.elf build tools/fontpack/linux.build
qemu-riscv64 build/fontpack.elf < assets/unifont/unifont-17.0.04.hex > build/suba-bmp.fnt
cmp build/suba-bmp.fnt assets/unifont/suba-bmp.fnt
```

正式字体由这份原生工具生成。Python 只在回归中独立构造预期字节和覆盖清单，不是生成正式字体的前置条件。系统盘应提供未压缩 `.hex`、`.fnt` 和上述许可文件，使系统内无需实现 gzip 就能重建字体；保留 `.gz` 仅供溯源/宿主复核，不是运行时依赖。

## SUBAFNT1 格式

所有整数小端；文件恰好 **2162704 B**：

|位置|内容|
|---|---|
|0..7|ASCII `SUBAFNT1`|
|8..11|u32 65536，BMP 索引数量|
|12..15|u32 16，字形高度|
|16..65551|65536 个宽度字节，0 缺字、8 半宽、16 全宽|
|65552..末尾|每码位固定 32 B：16 行，每行两字节，左侧像素是最高位|

半宽字形每行第二字节为零；缺字条目位图全部为零。glyph 索引就是 Unicode BMP 码位，无指针、宿主结构布局或隐式压缩。读取器验证固定头/长度、宽度取值和 surrogate 不得有字形。转换器拒绝超界、重复、未排序、非法 hex、surrogate 和非 8/16 宽输入；失败不修改输出缓冲，不写 stdout。
