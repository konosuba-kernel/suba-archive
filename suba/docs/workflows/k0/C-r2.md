# C-r2

r1独立验收发现BootInfo说明将kernel的base/end误写为地址/长度。已将说明明确为base与排他end的半开区间；没有改数值、VT实现、测试或平台。r1旧README保存在revisions/c-r1/abi/README.md，原候选和失败报告保留。r2清单更新唯一改变文件的hash，既有真实探针记录仍适用未变代码，由独立验收者复核后才接受。
