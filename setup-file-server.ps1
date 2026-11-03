param([Parameter(Mandatory=$true)][string]$DriveFolder)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (Test-Path -LiteralPath '.env.file-server') { throw 'Private server configuration already exists. Keep it and its storage identity; use start-file-server.ps1.' }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Install Python 3.12 or later and enable Add Python to PATH, then rerun setup.' }
$storeResult = & python file_server.py init --root $DriveFolder
if ($LASTEXITCODE -ne 0) { throw 'Drive initialization failed' }
$storageIdentity = ($storeResult | Where-Object { $_ -like 'FILE_STORAGE_ID=*' }) -replace '^FILE_STORAGE_ID=', ''
if (-not $storageIdentity) { throw 'No storage identity returned' }
$secretBytes = New-Object byte[] 48
$generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$generator.GetBytes($secretBytes)
$generator.Dispose()
$privateKey = [Convert]::ToBase64String($secretBytes)
$absoluteDriveFolder = (Resolve-Path -LiteralPath $DriveFolder).Path
[IO.File]::WriteAllLines((Join-Path $PSScriptRoot '.env.file-server'), @("FILE_STORAGE_ID=$storageIdentity", "FILE_STORAGE_TOKEN=$privateKey", "FILE_STORAGE_ROOT=$absoluteDriveFolder"), (New-Object System.Text.UTF8Encoding($false)))
Write-Host 'Drive initialized. Private settings were saved to .env.file-server. Keep that file private.'
Write-Host 'Run .\start-file-server.ps1 next. See COMPANY_FILE_SERVER.md for LAN and Vercel connection steps.'
