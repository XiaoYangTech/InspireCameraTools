// ============================================================================
// EasiCamera 2.0.10.4087 补丁后反编译证据（ILSpy 9.1.0.7988）
// 源: 完整 Main 副本（原始依赖齐全）中替换为补丁后 DLL 后反编译
// 补丁后：Visibility 为常量 Visible（SetValue），不再用 SeewoCameraButtonVisibilityConverter
// ============================================================================

	public ImageEnhanceDisplayToolBarItem()
	{
		base.SortHint = 101.0;
		base.FunctionModule = FunctionModule.MainWindow;
		SetValue(DisplayToolBarItem.VisibilityProperty, Visibility.Visible);
		Binding binding = new Binding
		{
			Path = new PropertyPath("CurrentSlide", null),
			Source = EC.BoardApi.Board,
			Converter = new SlideToButtonDisabledConverter()
		};
		BindingOperations.SetBinding(this, UiItem.IsCanClickDisabledProperty, binding);
	}
