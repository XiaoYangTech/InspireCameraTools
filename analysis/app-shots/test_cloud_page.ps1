$ErrorActionPreference = 'Stop'
$exe = "D:\开发\SeewoCamera\InspireCameraTools\dist\InspireCameraTools\InspireCameraTools.exe"
$outDir = "D:\开发\SeewoCamera\analysis\app-shots"
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class W32Cloud {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hwnd, IntPtr hdcBlt, uint nFlags);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, int dx, int dy, uint dwData, UIntPtr dwExtraInfo);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  public const uint WHEEL = 0x0800;
}
"@
function Capture-Window($hwnd, $outPath) {
  $r = New-Object W32Cloud+RECT
  [W32Cloud]::GetWindowRect($hwnd, [ref]$r) | Out-Null
  $w = $r.Right - $r.Left; $h = $r.Bottom - $r.Top
  $bmp = New-Object System.Drawing.Bitmap($w, $h)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $hdc = $g.GetHdc()
  [W32Cloud]::PrintWindow($hwnd, $hdc, 2) | Out-Null
  $g.ReleaseHdc($hdc); $g.Dispose()
  $bmp.Save($outPath, [System.Drawing.Imaging.ImageFormat]::Png)
  $bmp.Dispose()
  return @{ X = $r.Left; Y = $r.Top; W = $w; H = $h }
}
$p = Start-Process -FilePath $exe -ArgumentList "--page","settings" -PassThru
Start-Sleep -Seconds 7
$p.Refresh()
if ($p.HasExited) { Write-Host "APP EXITED"; exit 1 }
$hwnd = $p.MainWindowHandle
Write-Host "pid=$($p.Id) title=[$($p.MainWindowTitle)]"
[W32Cloud]::ShowWindowAsync($hwnd, 9) | Out-Null
[W32Cloud]::SetForegroundWindow($hwnd) | Out-Null
Start-Sleep -Milliseconds 600
$rect = Capture-Window $hwnd "$outDir\settings-cloud-top.png"
Write-Host "top: $($rect.W)x$($rect.H)"
# 滚动到云服务卡片
$cx = $rect.X + [int]($rect.W * 0.5)
$cy = $rect.Y + [int]($rect.H * 0.55)
[W32Cloud]::SetCursorPos($cx, $cy) | Out-Null
Start-Sleep -Milliseconds 200
for ($i = 0; $i -lt 5; $i++) {
  [W32Cloud]::mouse_event([W32Cloud]::WHEEL, 0, 0, [uint32]4294967176, [UIntPtr]::Zero)
  Start-Sleep -Milliseconds 150
}
Start-Sleep -Seconds 1
Capture-Window $hwnd "$outDir\settings-cloud.png" | Out-Null
Write-Host "saved settings-cloud.png"
