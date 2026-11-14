$ErrorActionPreference = 'Stop'
$exe = "D:\开发\SeewoCamera\InspireCameraTools\dist\InspireCameraTools\InspireCameraTools.exe"
$pastePath = "D:\开发\SeewoCamera\extracted\v2.1.0.4419\EasiCamera_2.1.0.4419\Main"
$outDir = "D:\开发\SeewoCamera\analysis\app-shots"

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class W32Paste {
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hwnd, IntPtr hdcBlt, uint nFlags);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, int dx, int dy, uint dwData, UIntPtr dwExtraInfo);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  public const uint LEFTDOWN = 0x0002;
  public const uint LEFTUP = 0x0004;
}
'@

function Capture-Window($hwnd, $outPath) {
  $r = New-Object W32Paste+RECT
  [W32Paste]::GetWindowRect($hwnd, [ref]$r) | Out-Null
  $w = $r.Right - $r.Left; $h = $r.Bottom - $r.Top
  $bmp = New-Object System.Drawing.Bitmap($w, $h)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $hdc = $g.GetHdc()
  [W32Paste]::PrintWindow($hwnd, $hdc, 2) | Out-Null
  $g.ReleaseHdc($hdc); $g.Dispose()
  $bmp.Save($outPath, [System.Drawing.Imaging.ImageFormat]::Png)
  $bmp.Dispose()
  return @{ X = $r.Left; Y = $r.Top; W = $w; H = $h }
}

Get-Process InspireCameraTools -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
Set-Clipboard -Value $pastePath
$p = Start-Process -FilePath $exe -ArgumentList "--page", "patch" -PassThru
Start-Sleep -Seconds 5
$p.Refresh()
if ($p.HasExited) { Write-Host "APP EXITED"; exit 1 }
$hwnd = $p.MainWindowHandle
if ($hwnd -eq [IntPtr]::Zero) { Write-Host "NO WINDOW"; exit 2 }
Write-Host "pid=$($p.Id) title=[$($p.MainWindowTitle)]"

$rect = Capture-Window $hwnd "$outDir\paste-before.png"
Write-Host "before: $($rect.W)x$($rect.H) at $($rect.X),$($rect.Y)"

# 激活窗口
[W32Paste]::ShowWindowAsync($hwnd, 9) | Out-Null
[W32Paste]::SetForegroundWindow($hwnd) | Out-Null
Start-Sleep -Milliseconds 800

# 点击 Main 目录输入框（窗口内相对坐标，按 1216x839 布局估算）
$clickX = $rect.X + [int]($rect.W * 0.25)
$clickY = $rect.Y + [int]($rect.H * 0.262)
[W32Paste]::SetCursorPos($clickX, $clickY) | Out-Null
Start-Sleep -Milliseconds 150
[W32Paste]::mouse_event([W32Paste]::LEFTDOWN, $clickX, $clickY, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 60
[W32Paste]::mouse_event([W32Paste]::LEFTUP, $clickX, $clickY, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 400

# 粘贴
[System.Windows.Forms.SendKeys]::SendWait("^v")
Start-Sleep -Seconds 2

$rect2 = Capture-Window $hwnd "$outDir\paste-after.png"
Write-Host "after: saved paste-after.png"
# 退出前不关闭程序，留给用户查看
Write-Host "APP KEPT RUNNING pid=$($p.Id)"
