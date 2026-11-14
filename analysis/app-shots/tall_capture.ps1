$ErrorActionPreference = 'Stop'
$outDir = "D:\开发\SeewoCamera\analysis\app-shots"
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class W32Resize {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
  [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int x, int y, int w, int h, bool repaint);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hwnd, IntPtr hdcBlt, uint nFlags);
  [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
$proc = Get-Process InspireCameraTools -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $proc) { Write-Host "NO APP"; exit 1 }
$proc.Refresh()
$hwnd = $proc.MainWindowHandle
[W32Resize]::ShowWindowAsync($hwnd, 9) | Out-Null
[W32Resize]::SetForegroundWindow($hwnd) | Out-Null
$r = New-Object W32Resize+RECT
[W32Resize]::GetWindowRect($hwnd, [ref]$r) | Out-Null
Write-Host "original $($r.Right-$r.Left)x$($r.Bottom-$r.Top) at $($r.Left),$($r.Top)"
[W32Resize]::MoveWindow($hwnd, $r.Left, 0, ($r.Right-$r.Left), 1700, $true) | Out-Null
Start-Sleep -Seconds 2
$r2 = New-Object W32Resize+RECT
[W32Resize]::GetWindowRect($hwnd, [ref]$r2) | Out-Null
$w = $r2.Right - $r2.Left; $h = $r2.Bottom - $r2.Top
Write-Host "resized ${w}x${h}"
$bmp = New-Object System.Drawing.Bitmap($w, $h)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
[W32Resize]::PrintWindow($hwnd, $hdc, 2) | Out-Null
$g.ReleaseHdc($hdc); $g.Dispose()
$bmp.Save("$outDir\settings-tall.png", [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
# 恢复原尺寸
[W32Resize]::MoveWindow($hwnd, $r.Left, $r.Top, ($r.Right-$r.Left), ($r.Bottom-$r.Top), $true) | Out-Null
Write-Host "saved settings-tall.png"
