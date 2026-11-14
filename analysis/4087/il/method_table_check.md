# 方法表对比：原版 vs 补丁后（证明只改指令字节、不改方法体长度/元数据布局）

方法：ILSpy `-il` 全程序集输出 → 解析每个方法的 `// Method begins at RVA` / `Header size` / `Code size`，逐方法比较。

| 程序集 | 方法数(原版) | 方法数(补丁后) | RVA/Header/CodeSize 差异数 |
|---|---|---|---|
| EasiCamera.UI.dll | 2286 | 2286 | 0 |
| EasiCamera.Business.dll | 880 | 880 | 0 |

结论：两个程序集全部方法的 RVA、方法头大小、IL 代码大小在补丁前后完全一致，
说明 6 处补丁全部是等长原地替换，没有移动任何方法体/异常表，元数据布局不变。

完整 IL 文本（较大，未入库）：`work/re4087/il/EasiCamera.UI.il.txt`（约 5.8MB）、
`work/re4087/il/EasiCamera.Business.il.txt`、`patched_UI.il.txt`、`patched_Business.il.txt`。
