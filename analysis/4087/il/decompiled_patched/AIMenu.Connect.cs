// ============================================================================
// EasiCamera 2.0.10.4087 补丁后反编译证据（ILSpy 9.1.0.7988）
// 源: 完整 Main 副本（原始依赖齐全）中替换为补丁后 DLL 后反编译
// 补丁后：case 2 英文批改按钮 Visibility=Collapsed（不再订阅 Click）
// ============================================================================

	void IComponentConnector.Connect(int connectionId, object target)
	{
		switch (connectionId)
		{
		case 1:
			OcrCorrectionButton = (IconButton)target;
			OcrCorrectionButton.Click += OcrCorrectionButton_OnClick;
			break;
		case 2:
			CompositionCorrectionButton = (IconButton)target;
			CompositionCorrectionButton.Visibility = Visibility.Collapsed;
			break;
		default:
			_contentLoaded = true;
			break;
		}
	}
