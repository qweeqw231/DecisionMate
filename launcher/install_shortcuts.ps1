# install_shortcuts.ps1 — 在桌面创建 DecisionMate / 测试台两个快捷方式
# 用法: powershell -ExecutionPolicy Bypass -File install_shortcuts.ps1
$ErrorActionPreference = 'Stop'

$dir = $PSScriptRoot
$desktop = [Environment]::GetFolderPath('Desktop')
$shell = New-Object -ComObject WScript.Shell

function New-Shortcut([string]$Name, [string]$CmdFile, [string]$IconFile, [string]$Desc) {
  $lnkPath = Join-Path $desktop $Name
  $lnk = $shell.CreateShortcut($lnkPath)
  $lnk.TargetPath = (Join-Path $dir $CmdFile)
  $lnk.WorkingDirectory = $dir
  $lnk.IconLocation = ((Join-Path $dir $IconFile) + ',0')
  $lnk.Description = $Desc
  $lnk.WindowStyle = 1
  $lnk.Save()
  Write-Host "created: $lnkPath"
}

New-Shortcut 'DecisionMate.lnk' 'DecisionMate.cmd' 'DecisionMate.ico' '个人决策支持系统：点击即用，关闭浏览器页面自动停止'
New-Shortcut 'DecisionMate 测试台.lnk' 'DecisionMateTest.cmd' 'DecisionMateTest.ico' '决策测试复核台：点击即用，关闭浏览器页面自动停止'