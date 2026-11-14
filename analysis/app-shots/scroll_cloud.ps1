$ErrorActionPreference = 'Stop'
$outDir = "D:\开发\SeewoCamera\analysis\app-shots"
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class W32Scroll {
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
$proc = Get-Process InspireCameraTools -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $proc) { Write-Host "NO APP"; exit 1 }
$proc.Refresh()
$hwnd = $proc.MainWindowHandle
[W32Scroll]::ShowWindowAsync($hwnd, 9) | Out-Null
[W32Scroll]::SetForegroundWindow($hwnd) | Out-Null
Start-Sleep -Milliseconds 500
$r = New-Object W32Scroll+RECT
[W32Scroll]::GetWindowRect($hwnd, [ref]$r) | Out-Null
$w = $r.Right - $r.Left; $h = $r.Bottom - $r.Top
$cx = $r.Left + [int]($w * 0.5)
$cy = $r.Top + [int]($h * 0.55)
[W32Scroll]::SetCursorPos($cx, $cy) | Out-Null
Start-Sleep -Milliseconds 200
for ($i = 0; $i -lt 18; $i++) {
  [W32Scroll]::mouse_event([W32Scroll]::WHEEL, 0, 0, [uint32]4294967176, [UIntPtr]::Zero)
  Start-Sleep -Milliseconds 100
}
Start-Sleep -Seconds 1
$bmp = New-Object System.Drawing.Bitmap($w, $h)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
[W32Scroll]::PrintWindow($hwnd, $hdc, 2) | Out-Null
$g.ReleaseHdc($hdc); $g.Dispose()
$bmp.Save("$outDir\settings-cloud2.png", [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Host "saved settings-cloud2.png"
