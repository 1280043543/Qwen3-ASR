param(
    [string]$InstallRoot = (Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference = 'Stop'
$pythonw = Join-Path $InstallRoot '.venv\Scripts\pythonw.exe'
$launcher = Join-Path $InstallRoot 'desktop-translator\launch.pyw'
if (-not (Test-Path -LiteralPath $pythonw)) { throw 'Python environment is not installed.' }
if (-not (Test-Path -LiteralPath $launcher)) { throw 'Desktop launcher is missing.' }

$shortcutName = '本地实时字幕'
$desktop = [Environment]::GetFolderPath('Desktop')
$programs = Join-Path ([Environment]::GetFolderPath('Programs')) $shortcutName
New-Item -ItemType Directory -Path $programs -Force | Out-Null
$icon = Join-Path $InstallRoot 'desktop-translator\qwen_local_subtitles\assets\app-icon.ico'
if (-not (Test-Path -LiteralPath $icon)) { $icon = $pythonw }

$wsh = New-Object -ComObject WScript.Shell
foreach ($folder in @($desktop, $programs)) {
    $shortcutPath = Join-Path $folder ($shortcutName + '.lnk')
    $shortcut = $wsh.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $pythonw
    $shortcut.Arguments = '"' + $launcher + '"'
    $shortcut.WorkingDirectory = $InstallRoot
    $shortcut.Description = '本地语音识别、翻译与悬浮字幕'
    $shortcut.IconLocation = $icon + ',0'
    $shortcut.Save()
    Write-Output $shortcutPath
}

