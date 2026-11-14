# 补丁后反编译证据（ILSpy 9.1.0.7988）

把补丁后的 `EasiCamera.UI.dll` / `EasiCamera.Business.dll` 放回**完整 Main 副本**（依赖程序集齐全）后反编译，避免缺引用导致的假类型警告。

- [AIMenu.Connect.cs](AIMenu.Connect.cs)
- [AIMenuDisplayToolBarItem.ctor.cs](AIMenuDisplayToolBarItem.ctor.cs)
- [CommonHidComponent.DataProcess_tail.cs](CommonHidComponent.DataProcess_tail.cs)
- [DisplayToolbar.BoardApiOnFunctionModuleChanged.cs](DisplayToolbar.BoardApiOnFunctionModuleChanged.cs)
- [DisplayToolbar.ctor_tail.cs](DisplayToolbar.ctor_tail.cs)
- [ImageEnhanceDisplayToolBarItem.ctor.cs](ImageEnhanceDisplayToolBarItem.ctor.cs)
