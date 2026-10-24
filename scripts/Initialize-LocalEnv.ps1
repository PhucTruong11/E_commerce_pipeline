[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$localSecrets = Join-Path $projectRoot '.local/secrets'
New-Item -ItemType Directory -Path $localSecrets -Force | Out-Null
foreach ($name in @('owner', 'reader')) {
    $secretPath = Join-Path $localSecrets "$name.password"
    if (-not (Test-Path -LiteralPath $secretPath)) {
        $bytes = [byte[]]::new(32)
        [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
        [IO.File]::WriteAllText($secretPath, [Convert]::ToHexString($bytes).ToLowerInvariant())
    }
}
$envPath = Join-Path $projectRoot '.env'
if (-not (Test-Path -LiteralPath $envPath)) {
    Copy-Item -LiteralPath (Join-Path $projectRoot 'config/.env.example') -Destination $envPath
}
Write-Host 'Local config ready. Existing files/passwords were preserved; no secrets printed.'
Write-Host 'Next: docker compose -f compose.shared.yaml config --quiet'
