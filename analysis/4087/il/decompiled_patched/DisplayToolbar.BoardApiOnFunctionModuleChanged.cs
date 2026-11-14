// ============================================================================
// EasiCamera 2.0.10.4087 补丁后反编译证据（ILSpy 9.1.0.7988）
// 源: 完整 Main 副本（原始依赖齐全）中替换为补丁后 DLL 后反编译
// 补丁后：flag 恒 false → 登录按钮始终保持 Collapsed
// ============================================================================

	private void BoardApiOnFunctionModuleChanged(object sender, FunctionModuleChangedEventArgs e)
	{
		FunctionModule newFunctionModule = e.NewFunctionModule;
		if ((newFunctionModule == FunctionModule.CompositionCorrection || newFunctionModule == FunctionModule.OcrCorrection) ? true : false)
		{
			CameraStackPanel.Children.Add(new CompositionToolBar(e.NewFunctionModule));
		}
		else
		{
			newFunctionModule = e.OldFunctionModule;
			if ((newFunctionModule == FunctionModule.CompositionCorrection || newFunctionModule == FunctionModule.OcrCorrection) ? true : false)
			{
				int count = CameraStackPanel.Children.Count;
				CameraStackPanel.Children.RemoveAt(count - 1);
			}
		}
		Cvte.GurnetUI.Controls.Button profileButton = ProfileButton;
		newFunctionModule = e.NewFunctionModule;
		bool flag = newFunctionModule != FunctionModule.MainWindow && newFunctionModule != FunctionModule.ContrastView && false;
		profileButton.Visibility = ((!flag) ? Visibility.Collapsed : Visibility.Visible);
	}
