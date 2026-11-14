$ErrorActionPreference = 'Stop'
$exe = "D:\开发\SeewoCamera\InspireCameraTools\dist\InspireCameraTools\InspireCameraTools.exe"
$outDir = "D:\开发\SeewoCamera\analysis\app-shots"
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class W32Wheel2 {
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
$p = Start-Process -FilePath $exe -ArgumentList "--page","settings" -PassThru
Start-Sleep -Seconds 7
$p.Refresh()
if ($p.HasExited) { Write-Host "APP EXITED"; exit 1 }
$hwnd = $p.MainWindowHandle
Write-Host "pid=$($p.Id) title=[$($p.MainWindowTitle)]"
[W32Wheel2]::ShowWindowAsync($hwnd, 9) | Out-Null
[W32Wheel2]::SetForegroundWindow($hwnd) | Out-Null
Start-Sleep -Milliseconds 800
$r = New-Object W32Wheel2+RECT
[W32Wheel2]::GetWindowRect($hwnd, [ref]$r) | Out-Null
$w = $r.Right - $r.Left; $h = $r.Bottom - $r.Top
# 指针放到内容区，直接滚轮（不再先拖滚动条）
$cx = $r.Left + [int]($w * 0.45)
$cy = $r.Top + [int]($h * 0.55)
[W32Wheel2]::SetCursorPos($cx, $cy) | Out-Null
Start-Sleep -Milliseconds 300
for ($i = 0; $i -lt 14; $i++) {
  [W32Wheel2]::mouse_event([W32Wheel2]::WHEEL, 0, 0, [uint32]4294967176, [UIntPtr]::Zero)
  Start-Sleep -Milliseconds 120
}
Start-Sleep -Seconds 1
$bmp = New-Object System.Drawing.Bitmap($w, $h)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
[W32Wheel2]::PrintWindow($hwnd, $hdc, 2) | Out-Null
$g.ReleaseHdc($hdc); $g.Dispose()
$bmp.Save("$outDir\settings-cloud-111.png", [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Host "saved settings-cloud-111.png"
