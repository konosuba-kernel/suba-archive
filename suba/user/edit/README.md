# K6 编辑核心接口

显式构建输入：`user/text/utf8.vt`、`user/edit/buffer.vt`、`user/edit/motion.vt`；模块名 `user::edit::buffer`。字体另外使用 `user/text/font.vt`，没有内核/FS/窗口依赖。

`unsafe open(storage, input)` 验证完整 UTF-8，返回带私有字段的 `Document`。storage 是调用者提供的独占长期内存，上限 **4 MiB**；input 是本次只读借用，不能与 storage 重叠。失败不修改输入或 storage；已有文档只在 Ready 时用新值替换。空文档/零容量有效，后续插入报告 NoMemory。

Document 是 gap buffer，gap 总在 cursor 位置；逻辑文本保持有效 UTF-8，cursor/anchor 始终是 Unicode scalar 字节边界。字段不可由使用者改写。S-next 仍按值复制结构，因此 Document 副本只是同一 backing 的别名；调用者必须保持单个逻辑所有者，串行调用，不能把结构复制视为复制了文档。

|操作|语义|
|---|---|
|`state(*const Document)`|bytes/capacity/cursor/anchor/version 快照；偏移单位为字节|
|`select(*Document, anchor, cursor)`|任一端不在边界返回 InvalidPosition，状态不变|
|`replace(*Document, bytes)`|以完整 UTF-8 替换选择；无选择则插入。非法、超限、容量不足、别名、版本耗尽均保持内容/光标/选择/version|
|`move(*Document, Motion, extend)`|左右按 scalar；行首/尾按 LF；文首/尾；extend 保留 anchor，否则折叠选择|
|`vertical(*Document, down, extend)`|上下按当前 scalar 列；短行截到行尾，不保存 sticky column，不等同像素列|
|`erase(*Document, backward)`|有选择删选择；否则后退/向前删一个完整 scalar；文档边界处无操作|
|`decode(*const Document, byte_offset)`|在逻辑文本任意边界解码，封装 gap 两侧；无效位置返回 Invalid|
|`snapshot(*const Document, out)`|把整个文档无损复制到独立输出；容量不足/别名时不改 out|
|`copy_selection(*const Document, out)`|进程内剪贴板复制；不修改文档；粘贴通过 replace，剪切仅在复制成功后 erase|
|`spans(*const Document)`|只读 prefix/suffix，拼接为精确文件字节；不得跨修改操作保留|
|`rehome(*Document, replacement)`|迁移到调用者已分配的新内存；失败旧状态不变，成功保持内容/cursor/anchor/version，旧 backing 由调用者回收|

`spans` 的任何旧视图在 select/move/replace/erase/rehome/open 重用 backing 后都失效，不能继续读取；rehome 成功后旧 backing 不再被 Document 引用，释放前仍须由调用者保证没有外部借用。复制剪贴板必须用独立存储；replace 会拒绝指向本 backing 的借用，避免移 gap 导致源被覆盖。核心不申请或释放内存，NoMemory 对应调用者未能提供足够存储；外层可分配后调用 rehome，分配失败时根本不改变 Document。

version 仅内容提交时递增；移动/选择/rehome 不递增。上层保存成功后记录 saved_version；编译诊断绑定编译时版本，版本不符先标旧诊断，再决定是否允许跳转。版本不回绕，耗尽返回 VersionLimit。当前没有 undo；保存、文件名、诊断 UI、构建作业属于 K7。

所有修改在失败检查之后才移动字节，单次复制/移动最多 4 MiB、无递归。它是可抢占用户进程中的同步核心，不是中断处理器或内核不可抢占工作片。保留 CR、LF、BOM、NUL、组合 scalar 和 4 字节字符的原字节；不做换行转换、归一化、grapheme、IME 或复杂排版。
