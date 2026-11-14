$ErrorActionPreference = 'Stop'
$pastePath = "D:\开发\SeewoCamera\extracted\v2.1.0.4419\EasiCamera_2.1.0.4419\Main"
$outDir = "D:\开发\SeewoCamera\analysis\app-shots"
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class W32P3 {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hwnd, IntPtr hdcBlt, uint nFlags);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, int dx, int dy, uint dwData, UIntPtr dwExtraInfo);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  public const uint LEFTDOWN = 0x0002;
  public const uint LEFTUP = 0x0004;
}
"@
function Capture-Window($hwnd, $outPath) {
  $r = New-Object W32P3+RECT
  [W32P3]::GetWindowRect($hwnd, [ref]$r) | Out-Null
  $w = $r.Right - $r.Left; $h = $r.Bottom - $r.Top
  $bmp = New-Object System.Drawing.Bitmap($w, $h)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $hdc = $g.GetHdc()
  [W32P3]::PrintWindow($hwnd, $hdc, 2) | Out-Null
  $g.ReleaseHdc($hdc); $g.Dispose()
  $bmp.Save($outPath, [System.Drawing.Imaging.ImageFormat]::Png)
  $bmp.Dispose()
  return @{ X = $r.Left; Y = $r.Top; W = $w; H = $h }
}
$proc = Get-Process InspireCameraTools -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $proc) { Write-Host "NO APP"; exit 1 }
$proc.Refresh()
$hwnd = $proc.MainWindowHandle
Write-Host "pid=$($proc.Id) hwnd=$hwnd title=[$($proc.MainWindowTitle)]"
$rect = Capture-Window $hwnd "$outDir\paste-before.png"
Write-Host "window $($rect.W)x$($rect.H) at $($rect.X),$($rect.Y)"
[W32P3]::ShowWindowAsync($hwnd, 9) | Out-Null
[W32P3]::SetForegroundWindow($hwnd) | Out-Null
Start-Sleep -Milliseconds 900
Write-Host "foreground=$([W32P3]::GetForegroundWindow() -eq $hwnd)"
Set-Clipboard -Value $pastePath
$clickX = $rect.X + [int]($rect.W * 0.28)
$clickY = $rect.Y + [int]($rect.H * 0.262)
Write-Host "click at $clickX,$clickY"
[W32P3]::SetCursorPos($clickX, $clickY) | Out-Null
Start-Sleep -Milliseconds 150
[W32P3]::mouse_event([W32P3]::LEFTDOWN, $clickX, $clickY, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 60
[W32P3]::mouse_event([W32P3]::LEFTUP, $clickX, $clickY, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 500
[System.Windows.Forms.SendKeys]::SendWait("^v")
Start-Sleep -Seconds 2
Capture-Window $hwnd "$outDir\paste-after.png" | Out-Null
Write-Host "saved paste-after.png"
