$ErrorActionPreference = 'Stop'
$exe = "D:\开发\SeewoCamera\InspireCameraTools\dist\InspireCameraTools\InspireCameraTools.exe"
$pastePath = "D:\开发\SeewoCamera\extracted\v2.1.0.4419\EasiCamera_2.1.0.4419\Main"
$outDir = "D:\开发\SeewoCamera\analysis\app-shots"

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class W32Paste2 {
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern int GetWindowTextW(IntPtr hWnd, StringBuilder sb, int max);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
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

  public static List<IntPtr> WindowsOf(uint targetPid, string titlePart) {
    var found = new List<IntPtr>();
    EnumWindows(delegate(IntPtr h, IntPtr l) {
      uint pid; GetWindowThreadProcessId(h, out pid);
      if (pid != targetPid) return true;
      if (!IsWindowVisible(h)) return true;
      var sb = new StringBuilder(512);
      GetWindowTextW(h, sb, 512);
      string title = sb.ToString();
      if (title.Length == 0) return true;
      if (titlePart.Length > 0 && title.IndexOf(titlePart, StringComparison.Ordinal) < 0) return true;
      RECT r; GetWindowRect(h, out r);
      if (r.Right - r.Left < 400) return true;
      found.Add(h);
      return true;
    }, IntPtr.Zero);
    return found;
  }
}
"@

function Capture-Window($hwnd, $outPath) {
  $r = New-Object W32Paste2+RECT
  [W32Paste2]::GetWindowRect($hwnd, [ref]$r) | Out-Null
  $w = $r.Right - $r.Left; $h = $r.Bottom - $r.Top
  $bmp = New-Object System.Drawing.Bitmap($w, $h)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $hdc = $g.GetHdc()
  [W32Paste2]::PrintWindow($hwnd, $hdc, 2) | Out-Null
  $g.ReleaseHdc($hdc); $g.Dispose()
  $bmp.Save($outPath, [System.Drawing.Imaging.ImageFormat]::Png)
  $bmp.Dispose()
  return @{ X = $r.Left; Y = $r.Top; W = $w; H = $h }
}

$proc = Get-Process InspireCameraTools -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $proc) {
  Set-Clipboard -Value $pastePath
  $proc = Start-Process -FilePath $exe -ArgumentList "--page", "patch" -PassThru
  Start-Sleep -Seconds 6
}
$proc.Refresh()
$wins = [W32Paste2]::WindowsOf([uint32]$proc.Id, "亿方展台管家")
Write-Host "pid=$($proc.Id) windows=$($wins.Count)"
if ($wins.Count -eq 0) { Write-Host "NO WINDOW"; exit 2 }
$hwnd = $wins[0]
$rect = Capture-Window $hwnd "$outDir\paste-before.png"
Write-Host "window $($rect.W)x$($rect.H) at $($rect.X),$($rect.Y)"

[W32Paste2]::ShowWindowAsync($hwnd, 9) | Out-Null
[W32Paste2]::SetForegroundWindow($hwnd) | Out-Null
Start-Sleep -Milliseconds 800
Write-Host "foreground=$([W32Paste2]::GetForegroundWindow() -eq $hwnd)"

Set-Clipboard -Value $pastePath
$clickX = $rect.X + [int]($rect.W * 0.28)
$clickY = $rect.Y + [int]($rect.H * 0.262)
Write-Host "click at $clickX,$clickY"
[W32Paste2]::SetCursorPos($clickX, $clickY) | Out-Null
Start-Sleep -Milliseconds 150
[W32Paste2]::mouse_event([W32Paste2]::LEFTDOWN, $clickX, $clickY, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 60
[W32Paste2]::mouse_event([W32Paste2]::LEFTUP, $clickX, $clickY, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 500
[System.Windows.Forms.SendKeys]::SendWait("^v")
Start-Sleep -Seconds 2
Capture-Window $hwnd "$outDir\paste-after.png" | Out-Null
Write-Host "saved paste-after.png"
