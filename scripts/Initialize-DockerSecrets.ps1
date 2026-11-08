$ErrorActionPreference = 'Stop'
$directory = Join-Path (Split-Path $PSScriptRoot -Parent) '.docker-secrets'
[void](New-Item -ItemType Directory -Path $directory -Force)
foreach ($name in @('postgres_password', 'redis_password')) {
    $target = Join-Path $directory $name
    if (Test-Path -LiteralPath $target) {
        if ((Get-Item -LiteralPath $target).Length -eq 0) {
            throw "Existing secret file is empty: $name. Resolve it before starting Docker."
        }
        continue
    }
    $bytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
        $value = [Convert]::ToBase64String($bytes)
        [IO.File]::WriteAllText($target, $value, (New-Object Text.UTF8Encoding($false)))
    } finally {
        $generator.Dispose()
        $value = $null
        [Array]::Clear($bytes, 0, $bytes.Length)
    }
}
Write-Output 'Docker secret files are ready; existing values were preserved.'
