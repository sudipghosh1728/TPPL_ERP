$ErrorActionPreference = 'Stop'
$previewRoot = $PSScriptRoot
$mongoBinary = Join-Path $previewRoot '.tools\mongod.exe'
$mongoDirectory = Join-Path $previewRoot '.tools\mongo-data'
$mongoLog = Join-Path $previewRoot '.tools\mongo-test.log'

if (-not (Get-NetTCPConnection -LocalPort 27018 -State Listen -ErrorAction SilentlyContinue)) {
    if (-not (Test-Path -LiteralPath $mongoBinary)) {
        throw 'Install the local test MongoDB replica set described in README.md first.'
    }
    Start-Process -FilePath $mongoBinary -ArgumentList "--dbpath `"$mongoDirectory`" --port 27018 --bind_ip 127.0.0.1 --replSet tppl-test --logpath `"$mongoLog`"" -WindowStyle Hidden
}

if (-not (Test-Path -LiteralPath (Join-Path $previewRoot 'public\website\index.html'))) {
    & python (Join-Path $previewRoot 'prepare_website.py')
    if ($LASTEXITCODE -ne 0) { throw 'Website build failed.' }
}

if (-not (Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue)) {
    $previewPython = (Get-Command python).Source
    Start-Process -FilePath $previewPython -ArgumentList 'local_preview.py --port 8001' -WorkingDirectory $previewRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $previewRoot '.tools\plant-preview.log') -RedirectStandardError (Join-Path $previewRoot '.tools\plant-preview-error.log')
}

Write-Output 'Local preview: http://localhost:8001/login.html'
Write-Output 'Admin: /admin | Departments: /user | Local MongoDB only. Email disabled.'
