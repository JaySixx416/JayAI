# Dot-source from the project directory: . ./Set-JayAIDatabase.ps1
# Credentials remain in this terminal and its child processes, never on disk.
$jayaiPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path $jayaiPython)) {
    $jayaiPython = Join-Path $PSScriptRoot '.venv/bin/python'
}
if (-not (Test-Path $jayaiPython)) {
    throw 'JayAI virtual environment not found. Use your existing project virtual environment.'
}
$jayaiSecurePassword = Read-Host 'JayAI database password' -AsSecureString
$jayaiPasswordPointer = [IntPtr]::Zero
try {
    $jayaiPasswordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($jayaiSecurePassword)
    $env:JAYAI_DB_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($jayaiPasswordPointer)
    $env:JAYAI_DB_HOST = '127.0.0.1'
    $env:JAYAI_DB_PORT = '5432'
    $env:JAYAI_DB_NAME = 'jayai'
    $env:JAYAI_DB_USER = 'jayai'
    & $jayaiPython -m jayai db-check
    if ($LASTEXITCODE -ne 0) {
        throw 'Database check failed. No migrations or PostgreSQL changes were performed.'
    }
} catch {
    Remove-Item Env:JAYAI_DB_PASSWORD -ErrorAction SilentlyContinue
    throw
} finally {
    if ($jayaiPasswordPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($jayaiPasswordPointer)
    }
    $jayaiSecurePassword.Dispose()
    Remove-Variable jayaiPasswordPointer, jayaiSecurePassword -ErrorAction SilentlyContinue
}
