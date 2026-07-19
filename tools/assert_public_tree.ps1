[CmdletBinding()]
param(
    [string]$RepositoryRoot
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = Split-Path -Parent $PSScriptRoot
}
$RepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
Set-Location -LiteralPath $RepositoryRoot

$forbiddenDirectoryPattern = '(^|/)(archive|reference|references|upstream|vendor|node_modules|out|dist|build|release|releases|logs|\.worktrees|\.vscode|\.idea|\.venv|venv|__pycache__|\.pytest_cache|superpowers)(/|$)'
$forbiddenExtensionPattern = '\.(package|ts4script|zip|7z|rar|pyc|pyo|log|sqlite|db|dll|exe|msi)$'
$forbiddenFilePattern = '(^|/)(BuildSummary\.json|GAMEPLAY_NOTES\.md|GAMEPLAY\.txt|\.env|\.env\..+|.*\.(pem|key|pfx|p12)|credentials[^/]*|secrets[^/]*)$|(^|/)[^/]*(?:_REFERENCE_|reference_logic)[^/]*$'
$secretPattern = 'ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,}|-----BEGIN( [A-Z]+)? PRIVATE KEY-----|sk-[A-Za-z0-9_-]{20,}'

$requiredFiles = @(
    'README.md',
    'LICENSE',
    'REDISTRIBUTION_AND_USE.md',
    'SUPPORTED_VERSIONS.md',
    '.gitignore',
    '.github/ISSUE_TEMPLATE/bug_report.yml',
    '.github/ISSUE_TEMPLATE/feature_request.yml',
    '.github/ISSUE_TEMPLATE/config.yml'
)

$paths = @(git ls-files --cached --others --exclude-standard)
$violations = [System.Collections.Generic.List[string]]::new()

foreach ($path in $paths) {
    $normalized = $path.Replace('\', '/')
    if ($normalized -match $forbiddenDirectoryPattern -or
        $normalized -match $forbiddenExtensionPattern -or
        $normalized -match $forbiddenFilePattern) {
        $violations.Add("Forbidden public path: $normalized")
    }
}

foreach ($requiredFile in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $RepositoryRoot $requiredFile))) {
        $violations.Add("Required public file is missing: $requiredFile")
    }
}

foreach ($path in $paths) {
    $fullPath = Join-Path $RepositoryRoot $path
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        continue
    }
    $file = Get-Item -LiteralPath $fullPath
    if ($file.Length -gt 5MB) {
        continue
    }
    if (Select-String -LiteralPath $fullPath -Pattern $secretPattern -Quiet -ErrorAction SilentlyContinue) {
        $violations.Add("Credential-pattern match: $($path.Replace('\', '/'))")
    }
}

if ($violations.Count -gt 0) {
    Write-Host 'Public-tree audit failed:' -ForegroundColor Red
    $violations | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
    exit 1
}

Write-Host "Public-tree audit passed: $($paths.Count) publishable paths checked." -ForegroundColor Green
