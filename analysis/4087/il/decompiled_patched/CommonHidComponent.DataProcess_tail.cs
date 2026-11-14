// ============================================================================
// EasiCamera 2.0.10.4087 补丁后反编译证据（ILSpy 9.1.0.7988）
// 源: 完整 Main 副本（原始依赖齐全）中替换为补丁后 DLL 后反编译
// 补丁后：cmd 13 分支为 ((ICommand)null)?.Execute(null)，即不再触发 OCR 菜单（截取方法尾部）
// ============================================================================

				}
				break;
			}
			case 1:
			case 2:
			{
				CameraInfo camera = EC.CameraApi.DeviceViewModel.MainPreViewElement.Camera;
				if (camera.Is8862Sc08UsbCamera())
				{
					camera.Mode = (CameraMode)b2;
					if (windowState != WindowState.Minimized)
					{
						EC.CameraApi.DeviceViewModel.SwitchToProperCamera(camera);
						NotifyUtil.ShowChangeModeTip();
					}
				}
				else
				{
					CameraInfo cameraInfo = EC.CameraApi.DeviceViewModel.Cameras.FirstOrDefault((CameraInfo \u0002) => CameraExtension.IsSpecificCamera(\u0002.DevicePath, this.m_\u0007, this.m_\u0008));
					if (cameraInfo != null)
					{
						cameraInfo.Mode = (CameraMode)b2;
					}
				}
				break;
			}
			}
		}
		if (data[2] == 11 && data.Length > 7)
		{
			byte b3 = data[6];
			Log.Info($"收到SC08热点回复 {b3}");
			if (b3 == 1)
			{
				string defaultWifiName = WlanUtil.DefaultWifiName;
				Path.Combine(EC.Path.ApplicationDataFolder, "wifi.xml");
				bool flag = WlanUtil.ConnectWifiWithRetryUsingDispatcher(defaultWifiName);
				Log.Info($"连接SC08热点结果 {flag}");
			}
		}
		if (data[2] == 13 && data.Length >= 7)
		{
			((ICommand)null)?.Execute((object)null);
		}
	}
