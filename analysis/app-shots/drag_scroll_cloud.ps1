$ErrorActionPreference = 'Stop'
$outDir = "D:\开发\SeewoCamera\analysis\app-shots"
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class W32Drag {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hwnd, IntPtr hdcBlt, uint nFlags);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, int dx, int dy, uint dwData, UIntPtr dwExtraInfo);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  public const uint LEFTDOWN = 0x0002;
  public const uint LEFTUP = 0x0004;
}
"@
$proc = Get-Process InspireCameraTools -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $proc) { Write-Host "NO APP"; exit 1 }
$proc.Refresh()
$hwnd = $proc.MainWindowHandle
[W32Drag]::ShowWindowAsync($hwnd, 9) | Out-Null
[W32Drag]::SetForegroundWindow($hwnd) | Out-Null
Start-Sleep -Milliseconds 500
$r = New-Object W32Drag+RECT
[W32Drag]::GetWindowRect($hwnd, [ref]$r) | Out-Null
$w = $r.Right - $r.Left; $h = $r.Bottom - $r.Top
# 拖动滚动条（右侧边缘）从顶部往下
$sx = $r.Left + $w - 12
$sy = $r.Top + 150
[W32Drag]::SetCursorPos($sx, $sy) | Out-Null
Start-Sleep -Milliseconds 200
[W32Drag]::mouse_event([W32Drag]::LEFTDOWN, $sx, $sy, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 150
for ($y = $sy; $y -lt ($r.Top + $h - 120); $y += 40) {
  [W32Drag]::SetCursorPos($sx, $y) | Out-Null
  Start-Sleep -Milliseconds 40
}
[W32Drag]::mouse_event([W32Drag]::LEFTUP, $sx, ($r.Top + $h - 120), 0, [UIntPtr]::Zero)
Start-Sleep -Seconds 1
$bmp = New-Object System.Drawing.Bitmap($w, $h)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
[W32Drag]::PrintWindow($hwnd, $hdc, 2) | Out-Null
$g.ReleaseHdc($hdc); $g.Dispose()
$bmp.Save("$outDir\settings-cloud3.png", [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Host "saved settings-cloud3.png"
