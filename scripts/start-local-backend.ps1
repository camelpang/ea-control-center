param(
    [int]$Port = 8001,
    [switch]$Reload,
    [switch]$StopExisting,
    [switch]$Foreground,
    [switch]$StopOnly,
    [int]$StartupTimeoutSec = 12
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $env:LocalAppData "Programs\Python\Python313\python.exe"
$baseUrl = "http://127.0.0.1:$Port"
$logDir = Join-Path $repoRoot ".local"
$stdoutLogPath = Join-Path $logDir "backend-$Port.out.log"
$stderrLogPath = Join-Path $logDir "backend-$Port.err.log"

if (-not (Test-Path $pythonExe)) {
    throw "Python 3.13 was not found at: $pythonExe"
}

function Get-PortOwners {
    param([int]$TargetPort)
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $TargetPort -ErrorAction SilentlyContinue)
    return @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
}

function Stop-PortOwners {
    param([int]$TargetPort)
    $owners = @(Get-PortOwners -TargetPort $TargetPort)
    foreach ($owner in $owners) {
        $process = Get-Process -Id $owner -ErrorAction SilentlyContinue
        if ($process) {
            Write-Host "Stopping existing process $owner on port $TargetPort ($($process.ProcessName))..." -ForegroundColor Yellow
            Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
        }
    }

    $deadline = (Get-Date).AddSeconds(5)
    do {
        Start-Sleep -Milliseconds 250
        $remaining = @(Get-PortOwners -TargetPort $TargetPort)
        if ($remaining.Count -eq 0) {
            return
        }
    } while ((Get-Date) -lt $deadline)

    throw "Port $TargetPort is still in use after stopping process id(s): $($remaining -join ', ')"
}

function Wait-BackendReady {
    param(
        [string]$Url,
        [int]$TimeoutSec
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing "$Url/health" -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                return $true
            }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    } while ((Get-Date) -lt $deadline)

    return $false
}

$existingOwners = @(Get-PortOwners -TargetPort $Port)
if ($existingOwners.Count -gt 0) {
    if ($StopExisting -or $StopOnly) {
        Stop-PortOwners -TargetPort $Port
    }
    else {
        $ownerText = $existingOwners -join ", "
        throw "Port $Port is already in use by process id(s): $ownerText. Rerun with -StopExisting, or stop only with -StopOnly."
    }
}

if ($StopOnly) {
    Write-Host "No backend is listening on port $Port." -ForegroundColor Green
    return
}

$reloadFlag = if ($Reload) { "enabled" } else { "disabled" }
$mode = if ($Foreground) { "foreground" } else { "detached" }

Write-Host "Starting EA Control Center local backend..." -ForegroundColor Cyan
Write-Host "Repo: $repoRoot"
Write-Host "Python: $pythonExe"
Write-Host "Port: $Port"
Write-Host "Reload: $reloadFlag"
Write-Host "Mode: $mode"
Write-Host "Admin UI:    $baseUrl/admin"
Write-Host "Dashboard:   $baseUrl/dashboard"
Write-Host "Manual ops:  $baseUrl/manual-trades"
Write-Host "Commands:    $baseUrl/commands"
Write-Host "Audit logs:  $baseUrl/audit-logs"
Write-Host "EA API base URL: $baseUrl"
Write-Host "EA_API_TOKEN: ea123456"
Write-Host "ADMIN_API_TOKEN: admin123456"

Push-Location $repoRoot
try {
    $uvicornArgs = @("-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", $Port)
    if ($Reload) {
        $uvicornArgs += "--reload"
    }

    if ($Foreground) {
        & $pythonExe @uvicornArgs
        return
    }

    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir | Out-Null
    }
    foreach ($path in @($stdoutLogPath, $stderrLogPath)) {
        if (Test-Path $path) {
            Remove-Item $path -Force
        }
    }

    $process = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList $uvicornArgs `
        -WorkingDirectory $repoRoot `
        -RedirectStandardOutput $stdoutLogPath `
        -RedirectStandardError $stderrLogPath `
        -PassThru `
        -WindowStyle Hidden

    Write-Host "Backend process started: $($process.Id)" -ForegroundColor Green
    Write-Host "Stdout log: $stdoutLogPath"
    Write-Host "Stderr log: $stderrLogPath"

    if (Wait-BackendReady -Url $baseUrl -TimeoutSec $StartupTimeoutSec) {
        Write-Host "Backend is ready: $baseUrl/health" -ForegroundColor Green
    }
    else {
        $owners = @(Get-PortOwners -TargetPort $Port)
        $ownerText = if ($owners.Count) { $owners -join ", " } else { "none" }
        throw "Backend did not become ready within $StartupTimeoutSec seconds. Port owner(s): $ownerText. Check logs: $stdoutLogPath and $stderrLogPath"
    }
}
finally {
    Pop-Location
}
