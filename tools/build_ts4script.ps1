param(
    [string]$Name = "PlumAntics_Simstrology",
    [string]$PycPython = "",
    [switch]$AllowIncompatiblePyc,
    [switch]$CleanOutput,
    [switch]$SourceOnly
)

$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "package_ts4script.py"
if (-not (Test-Path $scriptPath)) {
    throw "Missing script: $scriptPath"
}
$projectRoot = Split-Path $PSScriptRoot -Parent

$args = @(
    $scriptPath,
    "--name", $Name
)

$resolvedPycPython = $PycPython
if (-not $SourceOnly -and $resolvedPycPython -eq "") {
    $defaultPython37 = Join-Path $env:LOCALAPPDATA "Programs\Python\Python37\python.exe"
    if (Test-Path $defaultPython37) {
        $resolvedPycPython = $defaultPython37
    }
}

if (-not $SourceOnly -and $resolvedPycPython -eq "") {
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $pyLauncher) {
        try {
            $resolvedPycPython = (& $pyLauncher.Source -3.7 -c "import sys; print(sys.executable)").Trim()
        } catch {
            $resolvedPycPython = ""
        }
    }
}

if (-not $SourceOnly -and $resolvedPycPython -eq "") {
    throw "Could not resolve a Python 3.7 executable for compiled ts4script output. Use -PycPython <path> or -SourceOnly."
}

if ($resolvedPycPython -ne "") {
    $args += @("--pyc-python", $resolvedPycPython)
}
if ($AllowIncompatiblePyc) {
    $args += "--allow-incompatible-pyc"
}
if ($CleanOutput) {
    $args += "--clean-output"
}

$driver = Get-Command py -ErrorAction SilentlyContinue
if ($null -ne $driver) {
    Push-Location $projectRoot
    try {
        & $driver.Source -3.7 @args
        exit $LASTEXITCODE
    } finally {
        Pop-Location
    }
}

$driver = Get-Command python -ErrorAction SilentlyContinue
if ($null -ne $driver) {
    Push-Location $projectRoot
    try {
        & $driver.Source @args
        exit $LASTEXITCODE
    } finally {
        Pop-Location
    }
}

throw "Could not find a Python launcher. Install Python or make 'py'/'python' available on PATH."
