# K6 文本与字形

`user::text::utf8` 的 `decode` 返回 scalar 和下一个字节偏移，严格拒绝孤立续字节、截断、overlong、surrogate、U+10FFFF 以上值。`validate` 返回首个非法序列起始偏移；`boundary` / `previous` 的前提是已验证 UTF-8，前者检查位置，后者要求当前位置本身是边界。所有字节视图都是调用者的活跃只读借用，无隐式分配。

`user::text::font` 的 `open` 验证 SUBAFNT1 后返回 Font；调用者在 Font/Glyph 存活期间必须保持完整资源不可变。`glyph(font, scalar)` 返回 width、missing 和私有位图视图，`pixel(glyph,x,y)` 返回是否着色，越过字形/16行边界返回 false。8像素ASCII与16像素中文可由K5/K7绘制层逐像素着色；换行、tab、裁剪、窗口表面不属于字体模块。缺字方框保留16像素宽度，任何scalar原字节仍由编辑核心保留。

固定字体来源、精确覆盖、原生重建和许可见 [字体资源](../../assets/unifont/README.md)。字体 binary 的不可变借用与编辑 backing 的独占可变借用完全分开，没有以动态字体解析器或宿主字体服务替代本系统实现。
