# gen_icons.ps1 — 生成 DecisionMate 桌面图标（蓝底 + 橙色文字，多尺寸 PNG-in-ICO）
# 用法: powershell -ExecutionPolicy Bypass -File gen_icons.ps1
# 无需任何第三方依赖（使用 Windows 自带 .NET System.Drawing）
Add-Type -AssemblyName System.Drawing
$ErrorActionPreference = 'Stop'

$dir = $PSScriptRoot
$build = Join-Path $dir 'icon_build'
New-Item -ItemType Directory -Force -Path $build | Out-Null

function New-RoundedPath([int]$size, [int]$radius) {
  $p = New-Object System.Drawing.Drawing2D.GraphicsPath
  $d = $radius * 2
  $w = $size - 1
  $p.AddArc(0, 0, $d, $d, 180, 90)
  $p.AddArc($w - $d, 0, $d, $d, 270, 90)
  $p.AddArc($w - $d, $w - $d, $d, $d, 0, 90)
  $p.AddArc(0, $w - $d, $d, $d, 90, 90)
  $p.CloseFigure()
  return $p
}

function New-IconPng {
  param(
    [int]$Size,
    [string[]]$Lines,
    [string]$Bg,
    [string]$Fg,
    [string]$OutPath
  )
  $bmp = New-Object System.Drawing.Bitmap($Size, $Size)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
  $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
  $g.Clear([System.Drawing.Color]::Transparent)

  # 圆角蓝底
  $radius = [int][Math]::Max(2, $Size * 0.16)
  $path = New-RoundedPath $Size $radius
  $bgBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml($Bg))
  $g.FillPath($bgBrush, $path)

  # 自动收缩字号，直到所有行都放得下
  $maxW = [single]($Size * 0.84)
  $maxH = [single]($Size * 0.74)
  $fs = [Math]::Max(6, [int]($Size * 0.5))
  $font = $null
  while ($fs -gt 4) {
    $font = New-Object System.Drawing.Font('Segoe UI', [single]$fs, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
    $lineH = $fs * 1.15
    $totalH = $lineH * $Lines.Count
    $widest = 0.0
    foreach ($ln in $Lines) {
      $sz = $g.MeasureString($ln, $font)
      if ($sz.Width -gt $widest) { $widest = $sz.Width }
    }
    if ($widest -le $maxW -and $totalH -le $maxH) { break }
    $font.Dispose()
    $font = $null
    $fs--
  }
  if ($null -eq $font) {
    $font = New-Object System.Drawing.Font('Segoe UI', [single]5, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
  }

  # 橙色文字居中（多行）
  $fgBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml($Fg))
  $sfc = New-Object System.Drawing.StringFormat
  $sfc.Alignment = [System.Drawing.StringAlignment]::Center
  $sfc.LineAlignment = [System.Drawing.StringAlignment]::Center
  $lineH = $font.Size * 1.15
  $y = ($Size - $lineH * $Lines.Count) / 2.0
  foreach ($ln in $Lines) {
    $rect = New-Object System.Drawing.RectangleF(0, [single]$y, [single]$Size, [single]$lineH)
    $g.DrawString($ln, $font, $fgBrush, $rect, $sfc)
    $y += $lineH
  }

  $g.Dispose()
  $bmp.Save($OutPath, [System.Drawing.Imaging.ImageFormat]::Png)
  $bmp.Dispose()
}

function Pack-Ico {
  param([string[]]$PngPaths, [int[]]$Sizes, [string]$IcoPath)
  $blobs = @()
  foreach ($p in $PngPaths) { $blobs += , ([System.IO.File]::ReadAllBytes($p)) }

  $ms = New-Object System.IO.MemoryStream
  $bw = New-Object System.IO.BinaryWriter($ms)
  $bw.Write([UInt16]0)                # reserved
  $bw.Write([UInt16]1)                # type: icon
  $bw.Write([UInt16]$Sizes.Count)     # image count
  $offset = 6 + 16 * $Sizes.Count
  for ($i = 0; $i -lt $Sizes.Count; $i++) {
    $s = $Sizes[$i]
    $dim = if ($s -ge 256) { 0 } else { $s }   # 0 表示 256
    $len = $blobs[$i].Length
    $bw.Write([byte]$dim)
    $bw.Write([byte]$dim)
    $bw.Write([byte]0)
    $bw.Write([byte]0)
    $bw.Write([UInt16]1)
    $bw.Write([UInt16]32)
    $bw.Write([UInt32]$len)
    $bw.Write([UInt32]$offset)
    $offset += $len
  }
  foreach ($b in $blobs) { $bw.Write($b) }
  $bw.Flush()
  [System.IO.File]::WriteAllBytes($IcoPath, $ms.ToArray())
  $bw.Close()
}

$sizes = @(16, 32, 48, 64, 128, 256)

# 主程序图标：蓝底 + 橙字（小尺寸用 DM 缩写，大尺寸用全名两行）
$pngs = @()
foreach ($s in $sizes) {
  $lines = if ($s -lt 64) { @('DM') } else { @('Decision', 'Mate') }
  $out = Join-Path $build ("main_$s.png")
  New-IconPng -Size $s -Lines $lines -Bg '#1E40AF' -Fg '#F97316' -OutPath $out
  $pngs += $out
}
Pack-Ico -PngPaths $pngs -Sizes $sizes -IcoPath (Join-Path $dir 'DecisionMate.ico')

# 测试台图标：深一档的蓝底，大尺寸多一行 TEST 以便区分
$pngs = @()
foreach ($s in $sizes) {
  $lines = if ($s -lt 64) { @('DM') } else { @('Decision', 'Mate', 'TEST') }
  $out = Join-Path $build ("test_$s.png")
  New-IconPng -Size $s -Lines $lines -Bg '#0F2A6E' -Fg '#F97316' -OutPath $out
  $pngs += $out
}
Pack-Ico -PngPaths $pngs -Sizes $sizes -IcoPath (Join-Path $dir 'DecisionMateTest.ico')

Remove-Item $build -Recurse -Force
Write-Host "OK: DecisionMate.ico / DecisionMateTest.ico generated in $dir"