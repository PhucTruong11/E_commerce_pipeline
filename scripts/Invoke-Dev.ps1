[CmdletBinding()]
param(
    [ValidateSet('Build','Check','DbtDebug','Versions','Bootstrap','Extract')][string]$Action = 'Check',
    [ValidateSet('reader','owner')][string]$Role = 'reader',
    [Parameter(Mandatory)][string]$PlatformDir
)
$ErrorActionPreference = 'Stop'
if (($Action -eq 'Bootstrap' -and $Role -ne 'owner') -or
    ($Action -eq 'Extract' -and $Role -ne 'reader')) {
    throw 'Bootstrap requires -Role owner; Extract requires -Role reader.'
}
$projectRoot = Split-Path -Parent $PSScriptRoot
if ($Action -ne 'Build') {
    $secretFile = Join-Path $projectRoot ".local/secrets/$Role.password"
    if (-not (Test-Path -LiteralPath $secretFile -PathType Leaf)) {
        throw 'Expected a local password FILE for this role. Restore the provisioned secret; do not regenerate an existing DB password.'
    }
}
$policy = Get-Content -LiteralPath (Join-Path $PlatformDir 'resources.json') -Raw | ConvertFrom-Json
$task = $policy.projects.ecom.tasks.refresh
if (-not $task -or $task.memory_mib -le 0 -or $task.cpus -le 0) {
    throw 'Register ecom/refresh in the canonical resource policy first.'
}

# Manual CLI is deliberately excluded while the shared scheduler can launch work.
# This preflight is a snapshot: do not start other stacks during a manual command.
$ids = @(& docker ps -q)
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop is unavailable.' }
$live = @()
if ($ids.Count) {
    $inspectJson = & docker inspect @ids
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect running containers.' }
    $live = @($inspectJson | ConvertFrom-Json)
}
$runningMib = 0
foreach ($item in $live) {
    $labels = $item.Config.Labels
    if ($labels.'com.docker.compose.project' -eq 'airflow-platform' -and
        $labels.'com.docker.compose.service' -eq 'airflow-scheduler') {
        throw 'Manual window requires shared scheduler OFF. Use the registered Airflow operator after DAG integration.'
    }
    if ($item.HostConfig.Memory -le 0) { throw 'A running container has no RAM limit; resolve its budget first.' }
    $runningMib += $item.HostConfig.Memory / 1MB
}
$engineJson = & docker info --format '{{json .}}'
if ($LASTEXITCODE -ne 0) { throw 'Cannot read Engine capacity.' }
$engine = $engineJson | ConvertFrom-Json
$requiredMib = $runningMib + $task.memory_mib + $policy.headroom_mib + $policy.host.engine_overhead_mib
if ($requiredMib -gt $policy.host.memory_mib -or
    ($requiredMib - $policy.host.engine_overhead_mib) -gt ($engine.MemTotal / 1MB) -or
    $task.cpus -gt $engine.NCPU) { throw 'Not enough shared host budget for this manual runtime.' }
Write-Host "Manual budget: $requiredMib/$($policy.host.memory_mib) MiB, including runtime and reserves."

$previousMemory = $env:ECOM_RUNTIME_MEMORY_MIB
$previousCpus = $env:ECOM_RUNTIME_CPUS
$env:ECOM_RUNTIME_MEMORY_MIB = [string]$task.memory_mib
$env:ECOM_RUNTIME_CPUS = [string]$task.cpus
Push-Location $projectRoot
try {
    & docker compose -f compose.shared.yaml config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Compose validation failed; initialize local config first.' }
    if ($Action -eq 'Build') {
        & docker compose -f compose.shared.yaml build runtime
    } else {
        $service = if ($Role -eq 'owner') { 'owner' } else { 'runtime' }
        $command = switch ($Action) { Check { 'check' }; DbtDebug { 'dbt-debug' }; Versions { 'versions' }; Bootstrap { 'bootstrap' }; Extract { 'extract' } }
        & docker compose -f compose.shared.yaml run --rm --no-deps $service $command
    }
    if ($LASTEXITCODE -ne 0) { throw "Ecom $Action failed." }
} finally {
    Pop-Location
    $env:ECOM_RUNTIME_MEMORY_MIB = $previousMemory
    $env:ECOM_RUNTIME_CPUS = $previousCpus
}
