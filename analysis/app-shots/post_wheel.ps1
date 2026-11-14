$ErrorActionPreference = 'Stop'
$outDir = "D:\开发\SeewoCamera\analysis\app-shots"
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class W32Post {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hwnd, IntPtr hdcBlt, uint nFlags);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  public const uint WM_MOUSEWHEEL = 0x020A;
  public static void Wheel(IntPtr hwnd, int x, int y, int delta) {
    IntPtr wparam = (IntPtr)((delta & 0xFFFF) << 16);
    IntPtr lparam = (IntPtr)((y << 16) | (x & 0xFFFF));
    SendMessage(hwnd, WM_MOUSEWHEEL, wparam, lparam);
  }
}
"@
$proc = Get-Process InspireCameraTools -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $proc) { Write-Host "NO APP"; exit 1 }
$proc.Refresh()
$hwnd = $proc.MainWindowHandle
[W32Post]::ShowWindowAsync($hwnd, 9) | Out-Null
[W32Post]::SetForegroundWindow($hwnd) | Out-Null
Start-Sleep -Milliseconds 600
$r = New-Object W32Post+RECT
[W32Post]::GetWindowRect($hwnd, [ref]$r) | Out-Null
$w = $r.Right - $r.Left; $h = $r.Bottom - $r.Top
$cx = $r.Left + [int]($w * 0.45)
$cy = $r.Top + [int]($h * 0.55)
[W32Post]::SetCursorPos($cx, $cy) | Out-Null
for ($i = 0; $i -lt 16; $i++) {
  [W32Post]::Wheel($hwnd, $cx, $cy, -120)
  Start-Sleep -Milliseconds 120
}
Start-Sleep -Seconds 1
$bmp = New-Object System.Drawing.Bitmap($w, $h)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
[W32Post]::PrintWindow($hwnd, $hdc, 2) | Out-Null
$g.ReleaseHdc($hdc); $g.Dispose()
$bmp.Save("$outDir\settings-cloud-111b.png", [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Host "saved"
