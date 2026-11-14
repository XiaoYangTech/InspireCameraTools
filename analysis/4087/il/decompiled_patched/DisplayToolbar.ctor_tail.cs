// ============================================================================
// EasiCamera 2.0.10.4087 补丁后反编译证据（ILSpy 9.1.0.7988）
// 源: 完整 Main 副本（原始依赖齐全）中替换为补丁后 DLL 后反编译
// 补丁后：构造函数末尾 ProfileButton.Visibility=Collapsed（原为 DataContext=EC.Account）
// ============================================================================

	public DisplayToolbar()
	{
		InitializeComponent();
		base.Loaded += DisplayToolbar_Loaded;
		Modes.SwitchMode(Modes.RoamMode);
		EC.ImageApi.ImageCaptured += ImageApi_ImageCaptured;
		EC.AppConfig.AppTypeChanged += AppConfig_AppTypeChanged;
		EC.BoardApi.FunctionModuleChanged += BoardApiOnFunctionModuleChanged;
		DisplayToolBarItemViewModel viewModel = Cvte.Composition.Container.Current.Get<DisplayToolBarItemViewModel>();
		base.DataContext = viewModel;
		viewModel.SetWidthDetection(DetectRemainWidth);
		if (Application.Current.MainWindow is MainWindow mainWindow)
		{
			mainWindow.MainGrid.MouseDown += delegate
			{
				PopupHelper.CloseCurrentPopup();
			};
			mainWindow.MainGrid.PreviewTouchDown += delegate
			{
				PopupHelper.CloseCurrentPopup();
			};
			mainWindow.MainGrid.PreviewMouseDown += delegate
			{
				PopupHelper.CloseCurrentPopup();
			};
			mainWindow.SizeChanged += delegate
			{
				viewModel.RefreshUiItemState();
			};
		}
		_viewModel = Cvte.Composition.Container.Current.Get<ImageDiscernViewModel>();
		_viewModel.EnteredImageEnhance += ViewModel_EnteredImageEnhance;
		_viewModel.ExitedImageEnhance += ViewModel_ExitedImageEnhance;
		_viewModel.ImageDiscernStatusSwitched += ImageEnhanceService_ImageDiscernStatusSwitched;
		DefaultToolItemsControl.SizeChanged += DefaultToolItemsControlOnSizeChanged;
		EC.BoardApi.SidebarStatusChanged += BoardApi_SidebarStatusChanged;
		ProfileButton.Visibility = Visibility.Collapsed;
	}
