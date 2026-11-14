# 探查 EasiCamera 窗口的 UI Automation 树，找「拍照」等工具栏按钮
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$procList = Get-Process EasiCamera -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 }
if (-not $procList) { Write-Output "NO_WINDOW"; exit 1 }
$proc = $procList | Select-Object -First 1
Write-Output ("PROCESS {0} title={1} hwnd={2}" -f $proc.Id, $proc.MainWindowTitle, $proc.MainWindowHandle)

$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $proc.Id)
$win = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond)
if (-not $win) {
  $condTitle = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, $proc.MainWindowTitle)
  $win = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $condTitle)
}
if (-not $win) { Write-Output "WINDOW_NOT_FOUND"; exit 2 }
Write-Output ("WINDOW name=[{0}] class={1} type={2}" -f $win.Current.Name, $win.Current.ClassName, $win.Current.ControlType.ProgrammaticName)

$all = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
Write-Output ("DESCENDANTS {0}" -f $all.Count)
foreach ($e in $all) {
  try {
    $c = $e.Current
    $name = $c.Name
    $aid = $c.AutomationId
    if ([string]::IsNullOrWhiteSpace($name) -and [string]::IsNullOrWhiteSpace($aid)) { continue }
    $patterns = ""
    try {
      $ps = $e.GetSupportedPatterns()
      if ($ps) { $patterns = (($ps | ForEach-Object { $_.ProgrammaticName }) -join '|') }
    } catch {}
    $ct = $c.ControlType.ProgrammaticName -replace '^ControlType\.', ''
    Write-Output ("ROW|{0}|{1}|{2}|{3}|{4}|{5}" -f $ct, $name, $aid, $patterns, $c.IsEnabled, $c.IsOffscreen)
  } catch {}
}
