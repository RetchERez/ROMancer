function Open-ROMancerWindow {
    param([string]$Url,[string]$Workspace)
    $romancerWindowUri=[uri]$Url
    if ($romancerWindowUri.Scheme -ne 'http' -or $romancerWindowUri.Host -ne '127.0.0.1' -or $Url.Contains('"')) {throw 'Invalid local app address.'}
    $romancerLaunchId=[guid]::NewGuid().ToString('N')
    $romancerLaunchUri=New-Object System.UriBuilder($romancerWindowUri)
    $romancerLaunchUri.Query='launch='+$romancerLaunchId
    $romancerWindowUrl=$romancerLaunchUri.Uri.AbsoluteUri
    $romancerEdgePaths=@((Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'),(Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'))
    foreach ($romancerEdge in $romancerEdgePaths) {
        if (Test-Path -LiteralPath $romancerEdge -PathType Leaf) {
            try {
                $romancerBrowserProfile=Join-Path (Split-Path $Workspace -Parent) 'browser-profile'
                Start-Process -FilePath $romancerEdge -ArgumentList @(('--app="'+$romancerWindowUrl+'"'),('--user-data-dir="'+$romancerBrowserProfile+'"'),'--no-first-run') -WindowStyle Normal
                $romancerUiDeadline=[DateTime]::UtcNow.AddSeconds(8)
                $romancerStatusBody=@{operation='system.ui_status';parameters=@{launch_id=$romancerLaunchId}}|ConvertTo-Json -Compress
                while ([DateTime]::UtcNow -lt $romancerUiDeadline) {
                    try {
                        $romancerUi=Invoke-RestMethod -Uri ($romancerWindowUri.GetLeftPart('Authority')+'/api/call') -Method Post -ContentType 'application/json' -Headers @{Authorization=('Bearer '+$romancerWindowUri.Fragment.Replace('#token=',''))} -Body $romancerStatusBody -TimeoutSec 1
                        if ($romancerUi.ready) {Write-Output 'ROMancer desktop window is ready.';return}
                    } catch {}
                    Start-Sleep -Milliseconds 200
                }
                Write-Output 'Desktop window did not finish opening. Opening ROMancer in your browser.'
            } catch {Write-Output 'Opening ROMancer in your browser.'}
            Start-Process $romancerWindowUrl
            return
        }
    }
    Start-Process $romancerWindowUrl
}
