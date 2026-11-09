# Remove Yobi from this account: the program, its shortcuts, its Settings > Apps entry and
# "start with Windows". Yobi's data (keys, settings, what it learned) lives in the same folder.
param([string]$Links = '', [switch]$Silent)  # tests: -Links <the folder install.ps1 got>, -Silent: no questions
$ErrorActionPreference = 'Continue'
Add-Type -AssemblyName System.Windows.Forms
$Rtl = [System.Windows.Forms.MessageBoxOptions]::RtlReading -bor [System.Windows.Forms.MessageBoxOptions]::RightAlign
function Say($text, $icon = 'Information', $buttons = 'OK') {
    if ($Silent) { Write-Host "[say] $text"; return 'Yes' }
    [System.Windows.Forms.MessageBox]::Show($text, 'Yobi', $buttons, $icon, 'Button1', $Rtl)
}

$dest = Split-Path $PSScriptRoot -Parent          # this script lives in <install>/app
# only ever delete a real Yobi install (its own Python + launcher), never e.g. the source folder
if (-not ((Test-Path (Join-Path $dest 'runtime\pythonw.exe')) -and (Test-Path (Join-Path $dest 'app\launcher.pyw')))) {
    Say "ده مش فولدر يوبي متثبت:`n$dest" 'Error' | Out-Null; exit 1
}
$r = Say "تشيل يوبي من الجهاز؟`n`nهيتمسح البرنامج ومعاه مفاتيحك وإعداداته واللي اتعلمه." 'Question' 'YesNo'
if ($r -ne 'Yes') { exit 0 }

Set-Location $env:TEMP
Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($dest, 'OrdinalIgnoreCase') } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 800

$run = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$v = (Get-ItemProperty $run -Name Yobi -ErrorAction SilentlyContinue).Yobi
if ($v -and $v -like "*$dest*") { Remove-ItemProperty $run -Name Yobi -ErrorAction SilentlyContinue }
$key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Yobi'
if ((Get-ItemProperty $key -ErrorAction SilentlyContinue).InstallLocation -eq $dest) { Remove-Item $key -Recurse -Force }
# only the shortcuts that start this install (another copy's shortcuts stay)
# (shortcuts.py, not WScript.Shell: that one can't read an Arabic path on an English Windows)
$desk = if ($Links) { $Links.TrimEnd('\') } else { [Environment]::GetFolderPath('Desktop') }
$menu = if ($Links) { Join-Path $Links 'Menu' } else { Join-Path ([Environment]::GetFolderPath('Programs')) 'Yobi' }
& (Join-Path $dest 'runtime\python.exe') -s -E -B (Join-Path $dest 'app\shortcuts.py') remove $dest $desk $menu
Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue

if (Test-Path $dest) { Say "فاضل شوية ملفات في:`n$dest`nامسحها بإيدك بعد ما تعمل ريستارت." 'Warning' | Out-Null }
else { Say 'يوبي اتشال من الجهاز.' | Out-Null }
