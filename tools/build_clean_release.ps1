param(
    [string]$BuildVenv = ".buildenv",
    [string]$OutputRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $projectRoot "release_clean\NEX5SpikeLFPAnalyzer_$timestamp"
}

$outputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
$sourceStage = Join-Path $outputRoot "source"
$artifactsDir = Join-Path $outputRoot "artifacts"
$mainBuildDir = Join-Path $projectRoot ".release_build\main"
$decoderBuildDir = Join-Path $projectRoot ".release_build\decoder"
$mainDistDir = Join-Path $projectRoot ".release_dist\main"
$decoderDistDir = Join-Path $projectRoot ".release_dist\decoder"
$venvRoot = Join-Path $projectRoot $BuildVenv
$venvPython = Join-Path $venvRoot "Scripts\python.exe"
$venvPyInstaller = Join-Path $venvRoot "Scripts\pyinstaller.exe"
$isccCandidates = @(
    "C:\Users\$env:USERNAME\AppData\Local\Programs\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
$isccPath = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

function Invoke-CheckedCommand {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )
    Push-Location $WorkingDirectory
    try {
        & $FilePath @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed: $FilePath $($Arguments -join ' ')"
        }
    }
    finally {
        Pop-Location
    }
}

function New-CleanDirectory {
    param([string]$Path)
    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Path | Out-Null
}

function Copy-Tree {
    param(
        [string]$From,
        [string]$To
    )
    New-Item -ItemType Directory -Path $To -Force | Out-Null
    Copy-Item -Path (Join-Path $From "*") -Destination $To -Recurse -Force
}

if (-not (Test-Path $venvPython)) {
    & py -3.12 -m venv $venvRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create build venv."
    }
}

Invoke-CheckedCommand -FilePath $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel") -WorkingDirectory $projectRoot
Invoke-CheckedCommand -FilePath $venvPython -Arguments @("-m", "pip", "install", "-e", ".[dev]", "pyinstaller") -WorkingDirectory $projectRoot
Invoke-CheckedCommand -FilePath $venvPython -Arguments @("-m", "pytest", "-q", "tests\test_licensing.py", "tests\test_build_support.py") -WorkingDirectory $projectRoot

New-CleanDirectory -Path $outputRoot
New-CleanDirectory -Path $artifactsDir
New-CleanDirectory -Path $mainBuildDir
New-CleanDirectory -Path $decoderBuildDir
New-CleanDirectory -Path $mainDistDir
New-CleanDirectory -Path $decoderDistDir

Invoke-CheckedCommand -FilePath $venvPyInstaller -Arguments @(
    "--noconfirm",
    "--clean",
    "--distpath", $mainDistDir,
    "--workpath", $mainBuildDir,
    "NEX5SpikeLFPAnalyzer.spec"
) -WorkingDirectory $projectRoot

Invoke-CheckedCommand -FilePath $venvPyInstaller -Arguments @(
    "--noconfirm",
    "--clean",
    "--distpath", $decoderDistDir,
    "--workpath", $decoderBuildDir,
    "NEX5LicenseDecoder.spec"
) -WorkingDirectory $projectRoot

$mainAppDir = Join-Path $mainDistDir "NEX5SpikeLFPAnalyzer"
$decoderExe = Join-Path $decoderDistDir "NEX5LicenseDecoder.exe"
if (-not (Test-Path $mainAppDir)) {
    throw "Main app build output not found: $mainAppDir"
}
if (-not (Test-Path $decoderExe)) {
    throw "Decoder build output not found: $decoderExe"
}

if (-not $isccPath) {
    throw "Inno Setup 6 was not found. Install it first, then rerun tools\build_clean_release.ps1."
}

Invoke-CheckedCommand -FilePath $isccPath -Arguments @(
    "/Qp",
    "/DAppVersion=0.1.0",
    "/DAppSourceDir=$mainAppDir",
    "/DOutputDir=$artifactsDir",
    "installer\NEX5SpikeLFPAnalyzer.iss"
) -WorkingDirectory $projectRoot

Copy-Item -LiteralPath $decoderExe -Destination (Join-Path $artifactsDir "NEX5LicenseDecoder.exe") -Force

$sourceIncludes = @(
    ".gitignore",
    "README.md",
    "pyproject.toml",
    "launch_gui.py",
    "run_gui.bat",
    "build_exe.bat",
    "NEX5SpikeLFPAnalyzer.spec",
    "NEX5LicenseDecoder.spec",
    "license_public_key.pem"
)
$dirIncludes = @(
    "src",
    "tests",
    "tools",
    "installer"
)

New-Item -ItemType Directory -Path $sourceStage -Force | Out-Null
foreach ($item in $sourceIncludes) {
    Copy-Item -LiteralPath (Join-Path $projectRoot $item) -Destination $sourceStage -Force
}
foreach ($dir in $dirIncludes) {
    Copy-Tree -From (Join-Path $projectRoot $dir) -To (Join-Path $sourceStage $dir)
}

Get-ChildItem -Path $sourceStage -Recurse -Force -Directory |
    Where-Object { $_.Name -eq "__pycache__" -or $_.Name -like "*.egg-info" } |
    Remove-Item -Recurse -Force
Get-ChildItem -Path $sourceStage -Recurse -Force -File |
    Where-Object { $_.Extension -in @(".pyc", ".pyo") } |
    Remove-Item -Force

$notes = @"
交付目录说明
================

artifacts\
  NEX5SpikeLFPAnalyzer_Setup_0.1.0.exe   主程序安装版
  NEX5LicenseDecoder.exe                 解码查看工具免安装版

source\
  清理后的最新源码与打包脚本

构建时间: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
"@
$notes | Set-Content -LiteralPath (Join-Path $outputRoot "DELIVERY_README.txt") -Encoding UTF8

Write-Host ""
Write-Host "Clean release created at:"
Write-Host "  $outputRoot"
