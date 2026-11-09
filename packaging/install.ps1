# Yobi setup: copies Yobi into this account's programs folder, adds shortcuts and an entry in
# Settings > Apps. No admin rights needed. Running it again updates Yobi and keeps your data
# (keys, settings, what Yobi learned).
# Test options: -Dest <folder> -Links <folder> -Silent -NoLaunch (a test install skips the Settings > Apps entry)
param([string]$Dest = '', [string]$Links = '', [switch]$Silent, [switch]$NoLaunch)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$Rtl = [System.Windows.Forms.MessageBoxOptions]::RtlReading -bor [System.Windows.Forms.MessageBoxOptions]::RightAlign
function Say($text, $icon = 'Information', $buttons = 'OK') {
    if ($Silent) { Write-Host "[say] $text"; return 'No' }
    [System.Windows.Forms.MessageBox]::Show($text, 'Yobi', $buttons, $icon, 'Button1', $Rtl)
}

$src  = Split-Path $PSScriptRoot -Parent                       # ...\payload
$test = [bool]$Dest                                            # before the next line: $dest is the same variable
$dest = if ($Dest) { $Dest } else { Join-Path $env:LOCALAPPDATA 'Programs\Yobi' }
$dest = $dest.TrimEnd('\')
if ((Resolve-Path $src).Path.TrimEnd('\') -ieq $dest.TrimEnd('\')) { Say 'يوبي متثبت هنا بالفعل.'; exit 0 }
if (-not [Environment]::Is64BitOperatingSystem) { Say 'يوبي محتاج ويندوز 64 بت.' 'Error'; exit 1 }
if ([Environment]::OSVersion.Version.Major -lt 10) { Say 'يوبي محتاج ويندوز 10 أو 11.' 'Error'; exit 1 }

Write-Host 'Installing Yobi...'
# a running Yobi from an older install would lock its files
Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($dest, 'OrdinalIgnoreCase') } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 700

# runtime/ is all ours: mirror it. app/ also holds the user's data: copy over it, never delete.
& robocopy "$src\runtime" "$dest\runtime" /MIR /NFL /NDL /NJH /NJS /NP /R:2 /W:1 | Out-Null
if ($LASTEXITCODE -ge 8) { Say "النسخ وقف (robocopy $LASTEXITCODE). جرّب تاني بعد ما تقفل يوبي." 'Error'; exit 1 }
& robocopy "$src\app" "$dest\app" /E /NFL /NDL /NJH /NJS /NP /R:2 /W:1 | Out-Null
if ($LASTEXITCODE -ge 8) { Say "النسخ وقف (robocopy $LASTEXITCODE). جرّب تاني بعد ما تقفل يوبي." 'Error'; exit 1 }
Get-ChildItem $dest -Recurse -Include *.exe, *.dll, *.pyd -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue

$pyw  = Join-Path $dest 'runtime\pythonw.exe'
$app  = Join-Path $dest 'app'
$icon = Join-Path $app 'yobi.ico'
$desk = if ($Links) { $Links.TrimEnd('\') } else { [Environment]::GetFolderPath('Desktop') }
$menu = if ($Links) { Join-Path $Links 'Menu' } else { Join-Path ([Environment]::GetFolderPath('Programs')) 'Yobi' }
$run = "-s -E `"$app\launcher.pyw`""
$ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$uninstall = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$app\uninstall.ps1`""
# shortcuts.py makes them, not WScript.Shell: that one fails on an Arabic user name on an English Windows
& (Join-Path $dest 'runtime\python.exe') -s -E (Join-Path $app 'shortcuts.py') make $dest $desk $menu
if ($LASTEXITCODE -ne 0) { Say "يوبي اتثبت، بس معرفتش أعمل الاختصارات. شغّله من:`n$app\launcher.pyw" 'Warning' | Out-Null }

# Settings > Apps entry (this account only)
$key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Yobi'
if (-not $test) {
New-Item -Force $key | Out-Null
$mb = [int]((Get-ChildItem $dest -Recurse -File | Measure-Object Length -Sum).Sum / 1KB)
$props = @{ DisplayName = 'Yobi'; Publisher = 'Yobi'; DisplayIcon = $icon; InstallLocation = $dest
            UninstallString = "`"$ps`" $uninstall"; NoModify = 1; NoRepair = 1; EstimatedSize = $mb }
foreach ($k in $props.Keys) {
    $type = if ($props[$k] -is [int]) { 'DWord' } else { 'String' }
    New-ItemProperty -Path $key -Name $k -Value $props[$k] -PropertyType $type -Force | Out-Null
}
}

# the island needs Microsoft Edge WebView2 (already on Windows 11 and most Windows 10)
$wv = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
$hasWv = @("HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$wv", "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$wv",
           "HKCU:\Software\Microsoft\EdgeUpdate\Clients\$wv") |
    Where-Object { (Get-ItemProperty $_ -ErrorAction SilentlyContinue).pv -and (Get-ItemProperty $_).pv -ne '0.0.0.0' }
if (-not $hasWv) {
    $r = Say "الجزيرة بتاعة يوبي محتاجة Microsoft Edge WebView2، ومش لاقيه على الجهاز.`n`nأفتحلك صفحة التحميل؟ (مجاني من مايكروسوفت)" 'Warning' 'YesNo'
    if ($r -eq 'Yes') { Start-Process 'https://developer.microsoft.com/microsoft-edge/webview2/' }
}

Write-Host 'Done.'
Say "يوبي اتثبت ✅`n`nهتلاقيه على سطح المكتب وفي قايمة ابدأ. أول مرة هيطلب منك مفتاح Gemini المجاني.`n`nكلّمه بـ «يا يوبي» أو دوس Ctrl + Alt + Y." | Out-Null
if (-not $NoLaunch) { Start-Process $pyw -ArgumentList $run -WorkingDirectory $app }
