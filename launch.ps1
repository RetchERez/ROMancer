param(
    [switch]$Check,
    [switch]$NoBrowser,
    [int]$Port = 0,
    [string]$Workspace = '',
    [string]$PythonPath = ''
)
$ErrorActionPreference = 'Stop'
$romancerRoot = $PSScriptRoot
. (Join-Path $PSScriptRoot 'desktop_window.ps1')
$romancerProductVersion = ([regex]::Match((Get-Content -LiteralPath (Join-Path $PSScriptRoot 'romancer\__init__.py') -Raw),'ROMANCER_VERSION = [\x22]([^\x22]+)[\x22]')).Groups[1].Value
if (-not $Workspace) { $Workspace = Join-Path $env:LOCALAPPDATA 'ROMancer\workspace' }
if ($Port -lt 0 -or $Port -gt 65535) { throw 'Port must be between 0 and 65535. Use 0 to choose an available port.' }
$romancerCandidates = @()
if ($PythonPath) { $romancerCandidates = @($PythonPath) }
elseif ($env:ROMANCER_PYTHON) { $romancerCandidates = @($env:ROMANCER_PYTHON) }
else {
    $romancerBundled = Join-Path (Split-Path $PSScriptRoot -Parent) 'python\python.exe'
    if (Test-Path -LiteralPath $romancerBundled -PathType Leaf) { $romancerCandidates += $romancerBundled }
    $romancerCandidates += 'C:\Python314\python.exe'
    $romancerPythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($romancerPythonCommand) { $romancerCandidates += $romancerPythonCommand.Source }
    $romancerPyCommand = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($romancerPyCommand) {
        foreach ($romancerPythonSelector in @('-3.14','-3.13')) {
            try {
                $romancerResolved = & $romancerPyCommand.Source $romancerPythonSelector -I -c 'import sys;print(sys.executable)' 2>$null
                if ($LASTEXITCODE -eq 0) { $romancerCandidates += $romancerResolved }
            } catch {}
        }
    }
}
$romancerPython = $null
foreach ($romancerCandidate in $romancerCandidates | Select-Object -Unique) {
    if (-not (Test-Path -LiteralPath $romancerCandidate -PathType Leaf)) { continue }
    try {
        $romancerProbeCode = "import sys,importlib.util,json;ok=sys.version_info>=(3,13) and importlib.util.find_spec('PIL') is not None;print(json.dumps(dict(ok=ok,python=sys.executable,version=sys.version.split()[0])));sys.exit(0 if ok else 1)"
        $romancerProbe = & $romancerCandidate -I -c $romancerProbeCode 2>$null
        if ($LASTEXITCODE -eq 0) { $romancerPython = $romancerCandidate; break }
    } catch {}
}
if (-not $romancerPython) {
    throw 'ROMancer needs Python 3.13 or newer with Pillow. Install Python, run: py -3.14 -m pip install -r requirements.txt, then relaunch. Set ROMANCER_PYTHON to select a specific python.exe.'
}
if ($Check) { Write-Output $romancerProbe; exit 0 }
New-Item -ItemType Directory -Path $Workspace -Force | Out-Null
$romancerConnection = Join-Path $Workspace 'connection.json'
if (Test-Path -LiteralPath $romancerConnection) {
    try {
        $romancerExisting = Get-Content -LiteralPath $romancerConnection -Raw | ConvertFrom-Json
        $romancerExistingUrl = [uri]$romancerExisting.url
        if ($romancerExisting.application_root -ieq $romancerRoot -and $romancerExistingUrl.Host -eq '127.0.0.1' -and $romancerExistingUrl.Scheme -eq 'http') {
            $romancerExistingToken = $romancerExistingUrl.Fragment.Replace('#token=','')
            $romancerResponse = Invoke-RestMethod -Uri ($romancerExistingUrl.GetLeftPart('Authority') + '/api/call') -Method Post -ContentType 'application/json' -Headers @{Authorization=('Bearer ' + $romancerExistingToken)} -Body '{"operation":"system.capabilities","parameters":{}}' -TimeoutSec 2
            if ($romancerResponse.ok -and $romancerResponse.product -eq 'ROMancer' -and $romancerResponse.version -eq $romancerProductVersion) {
                if (-not $NoBrowser) { Open-ROMancerWindow -Url $romancerExisting.url -Workspace $Workspace }
                Write-Output 'Reopened the existing local ROMancer session.'
                exit 0
            }
        }
    } catch {}
}
$romancerArguments = @('-B','-m','romancer.workbench_server','--workspace',('"' + $Workspace + '"'),'--port',[string]$Port,'--no-browser')
$romancerProcess = Start-Process -FilePath $romancerPython -ArgumentList $romancerArguments -WorkingDirectory $romancerRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $Workspace 'server.log') -RedirectStandardError (Join-Path $Workspace 'server-errors.log')
$romancerDeadline = [DateTime]::UtcNow.AddSeconds(15)
$romancerReady = $false
while ([DateTime]::UtcNow -lt $romancerDeadline) {
    if ($romancerProcess.HasExited) { break }
    if (Test-Path -LiteralPath $romancerConnection) {
        try {
            $romancerInfo = Get-Content -LiteralPath $romancerConnection -Raw | ConvertFrom-Json
            if ($romancerInfo.pid -eq $romancerProcess.Id) { $romancerReady = $true; break }
        } catch {}
    }
    Start-Sleep -Milliseconds 150
    $romancerProcess.Refresh()
}
if (-not $romancerReady) {
    if (-not $romancerProcess.HasExited) { Stop-Process -Id $romancerProcess.Id }
    throw ('ROMancer could not start. Choose another port or use port 0. Details: ' + (Join-Path $Workspace 'server-errors.log'))
}
if (-not $NoBrowser) { Open-ROMancerWindow -Url $romancerInfo.url -Workspace $Workspace }
Write-Output ('ROMancer is ready at http://127.0.0.1:' + $romancerInfo.port + '/ — By RetchEWretched')
