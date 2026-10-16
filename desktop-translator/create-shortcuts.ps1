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
$shortcutPaths = @((Join-Path $desktop ($shortcutName + '.lnk')), (Join-Path $programs ($shortcutName + '.lnk')))
$pinnedFolder = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar'
if (Test-Path -LiteralPath $pinnedFolder) {
    foreach ($file in Get-ChildItem -LiteralPath $pinnedFolder -Filter '*.lnk') {
        $pinned = $wsh.CreateShortcut($file.FullName)
        if ($pinned.Arguments.Contains($launcher) -or ($pinned.TargetPath -eq $pythonw -and $pinned.WorkingDirectory -eq $InstallRoot)) {
            $shortcutPaths += $file.FullName
        }
    }
}
foreach ($shortcutPath in $shortcutPaths) {
    $shortcut = $wsh.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $pythonw
    $shortcut.Arguments = '"' + $launcher + '"'
    $shortcut.WorkingDirectory = $InstallRoot
    $shortcut.Description = '本地语音识别、翻译与悬浮字幕'
    $shortcut.IconLocation = $icon + ',0'
    $shortcut.Save()
    Write-Output $shortcutPath
}
$python = Join-Path $InstallRoot '.venv\Scripts\python.exe'
& $python -m qwen_local_subtitles.windows_shell @shortcutPaths
if ($LASTEXITCODE -ne 0) { throw 'Unable to set taskbar identity on shortcuts.' }


