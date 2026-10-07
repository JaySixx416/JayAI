[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8000,
    [switch]$SkipMigrations
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "JayAI Python environment not found at $python. Follow docs/STANDALONE.md first."
}

$names = @(
    'JAYAI_DATABASE_URL', 'JAYAI_DB_PASSWORD', 'JAYAI_DB_HOST', 'JAYAI_DB_PORT',
    'JAYAI_DB_NAME', 'JAYAI_DB_USER', 'JAYAI_ENV', 'JAYAI_DEV_USER_ID',
    'JAYAI_DEV_API_KEY', 'JAYAI_LOCAL_MODEL'
)
$original = @{}
foreach ($name in $names) {
    $original[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$secret = $null
$pointer = [IntPtr]::Zero

try {
    if (-not $env:JAYAI_DATABASE_URL -and -not $env:JAYAI_DB_PASSWORD) {
        $secret = Read-Host 'JayAI PostgreSQL password' -AsSecureString
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
        $env:JAYAI_DB_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
        if (-not $env:JAYAI_DB_HOST) { $env:JAYAI_DB_HOST = '127.0.0.1' }
        if (-not $env:JAYAI_DB_PORT) { $env:JAYAI_DB_PORT = '5432' }
        if (-not $env:JAYAI_DB_NAME) { $env:JAYAI_DB_NAME = 'jayai' }
        if (-not $env:JAYAI_DB_USER) { $env:JAYAI_DB_USER = 'jayai' }
    }

    & $python -m jayai db-check
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL connection check failed; JayAI was not started.' }
    if (-not $SkipMigrations) {
        & $python -m jayai migrate
        if ($LASTEXITCODE -ne 0) { throw 'Database migrations failed; JayAI was not started.' }
    }

    if (-not $env:JAYAI_DEV_USER_ID) {
        $profileDirectory = Join-Path $env:LOCALAPPDATA 'JayAI'
        $null = New-Item -ItemType Directory -Path $profileDirectory -Force
        $profilePath = Join-Path $profileDirectory 'development-user-id.txt'
        if (Test-Path -LiteralPath $profilePath -PathType Leaf) {
            $savedUserId = (Get-Content -LiteralPath $profilePath -Raw).Trim()
            $parsedUserId = [Guid]::Empty
            if (-not [Guid]::TryParse($savedUserId, [ref]$parsedUserId)) {
                throw "Stored JayAI development user ID is invalid: $profilePath"
            }
            $env:JAYAI_DEV_USER_ID = $parsedUserId.ToString()
        } else {
            $created = & $python -m jayai create-dev-user
            if ($LASTEXITCODE -ne 0) { throw 'Could not create the JayAI development user.' }
            $match = [regex]::Match(($created | Out-String), 'Development user ID:\s*([0-9a-fA-F-]{36})')
            if (-not $match.Success) { throw 'JayAI did not return a valid development user ID.' }
            $env:JAYAI_DEV_USER_ID = ([Guid]$match.Groups[1].Value).ToString()
            [IO.File]::WriteAllText($profilePath, $env:JAYAI_DEV_USER_ID, [Text.UTF8Encoding]::new($false))
        }
    }

    if (-not $env:JAYAI_DEV_API_KEY) {
        $keyBytes = New-Object byte[] 32
        $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($keyBytes) } finally { $rng.Dispose() }
        $env:JAYAI_DEV_API_KEY = [BitConverter]::ToString($keyBytes).Replace('-', '').ToLowerInvariant()
        [Array]::Clear($keyBytes, 0, $keyBytes.Length)
    }

    $env:JAYAI_ENV = 'development'
    if (-not $env:JAYAI_LOCAL_MODEL) { $env:JAYAI_LOCAL_MODEL = 'qwen2.5:0.5b' }
    Write-Host "JayAI is starting on http://127.0.0.1:$Port/"
    Write-Host 'Keep this PowerShell window open. Stop JayAI with Ctrl+C.'
    Write-Host "Dashboard key for this run: $env:JAYAI_DEV_API_KEY"
    & $python -m uvicorn jayai.main:app --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE -ne 0) { throw "JayAI stopped with exit code $LASTEXITCODE." }
} finally {
    if ($pointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
    if ($secret) { $secret.Dispose() }
    foreach ($name in $names) {
        [Environment]::SetEnvironmentVariable($name, $original[$name], 'Process')
    }
}
