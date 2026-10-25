$ErrorActionPreference = 'Stop'
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = $PSScriptRoot
    if ($previousPythonPath) {
        $env:PYTHONPATH += [IO.Path]::PathSeparator + $previousPythonPath
    }
    $romancerBundled = Join-Path (Split-Path $PSScriptRoot -Parent) 'python\python.exe'
    if (Test-Path -LiteralPath $romancerBundled -PathType Leaf) {
        & $romancerBundled -I -B -u -m romancer @args
    } else {
        & python -P -u -m romancer @args
    }
    $exitCode = $LASTEXITCODE
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}
exit $exitCode
