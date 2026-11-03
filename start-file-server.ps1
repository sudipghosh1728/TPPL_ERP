$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.env.file-server')) { throw 'Run setup-file-server.ps1 first.' }
$driveLine = Get-Content -LiteralPath '.env.file-server' | Where-Object { $_ -like 'FILE_STORAGE_ROOT=*' } | Select-Object -First 1
if (-not $driveLine) { throw 'FILE_STORAGE_ROOT is missing from .env.file-server' }
$driveFolder = $driveLine.Substring('FILE_STORAGE_ROOT='.Length)
& python file_server.py serve --root $driveFolder --config .env.file-server
