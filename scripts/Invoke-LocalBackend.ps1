param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Migrate', 'Test', 'Worker', 'MarketplaceKeys')]
    [string]$Action,
    [string]$OrganizationId
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$backend = Join-Path $root 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Create backend\.venv and install backend\requirements-dev.txt first.'
}
if ($Action -eq 'MarketplaceKeys') {
    Push-Location $backend
    try {
        & $python -m app.modules.marketplace.crypto --generate-development-keys (Join-Path $root '.docker-secrets')
        if ($LASTEXITCODE -ne 0) { throw 'Marketplace key generation failed.' }
    } finally { Pop-Location }
    return
}
if ($Action -eq 'Test') {
    Push-Location $backend
    try {
        & $python -m pytest -q
        if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }
    } finally { Pop-Location }
    return
}

$user = 'crm_api'
if ($Action -eq 'Migrate') {
    $user = 'crm_migrator'
}
if ($Action -eq 'Worker') {
    if (-not $OrganizationId) { throw 'Worker requires -OrganizationId from your signed-in account identity.' }
    $user = 'crm_worker'
}
$secretFile = Join-Path $root '.docker-secrets\postgres_password'
if (-not (Test-Path -LiteralPath $secretFile)) {
    throw 'Run scripts\Initialize-DockerSecrets.ps1 before using the database.'
}
$password = [IO.File]::ReadAllText($secretFile).Trim()
if (-not $password) { throw 'The required database secret is empty.' }
$previousUrl = $env:DATABASE_URL
$previousEnvironment = $env:APP_ENVIRONMENT
$previousAuthUrl = $env:AUTH_DATABASE_URL
$previousMarketplaceKey = $env:MARKETPLACE_PUBLIC_KEY_FILE
try {
    $encoded = [Uri]::EscapeDataString($password)
    $env:DATABASE_URL = "postgresql+psycopg://${user}:${encoded}@127.0.0.1:55432/leadberry"
    $env:APP_ENVIRONMENT = 'development'
    $env:AUTH_DATABASE_URL = $null
    $publicKey = Join-Path $root '.docker-secrets\marketplace-public.pem'
    if (Test-Path -LiteralPath $publicKey) { $env:MARKETPLACE_PUBLIC_KEY_FILE = $publicKey }
    Push-Location $backend
    try {
        if ($Action -eq 'Migrate') {
            & $python -m alembic upgrade head
            if ($LASTEXITCODE -ne 0) { throw 'Migration failed; runtime grants were not applied.' }
        } else {
            & $python -m app.modules.marketplace.worker --organization $OrganizationId --private-key (Join-Path $root '.docker-secrets\marketplace-private.pem')
            if ($LASTEXITCODE -ne 0) { throw 'Connector worker exited with an error.' }
        }
    } finally { Pop-Location }
} finally {
    $env:DATABASE_URL = $previousUrl
    $env:APP_ENVIRONMENT = $previousEnvironment
    $env:AUTH_DATABASE_URL = $previousAuthUrl
    $env:MARKETPLACE_PUBLIC_KEY_FILE = $previousMarketplaceKey
    Remove-Variable password, encoded -ErrorAction SilentlyContinue
}
