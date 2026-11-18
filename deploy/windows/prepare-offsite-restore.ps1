param(
    [string]$Server = '120.24.108.60',
    [string]$BackupId,
    [string]$BackupRoot = "$env:USERPROFILE\FinSentinelBackups",
    [string]$AgeIdentity = "$env:USERPROFILE\finsentinel-age-key.txt",
    [string]$KnownHosts = "$env:LOCALAPPDATA\FinSentinel\ssh_known_hosts",
    [switch]$Send
)

$ErrorActionPreference = 'Stop'
$appRoot = Join-Path $env:LOCALAPPDATA 'FinSentinel'
$clientRoot = Join-Path $appRoot 'client'
$ageExe = Join-Path $clientRoot 'age\age.exe'
$sshExe = (Get-Command ssh.exe -ErrorAction Stop).Source
$sshKeygen = (Get-Command ssh-keygen.exe -ErrorAction Stop).Source
$python = (Get-Command python.exe -ErrorAction Stop).Source
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

foreach ($path in @($AgeIdentity,$KnownHosts,$ageExe)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file missing: $path" }
}
if (-not $BackupId) {
    $latest = Get-ChildItem -LiteralPath $BackupRoot -Filter 'backup-*.tar.gz.age' -File |
        Sort-Object Name -Descending | Select-Object -First 1
    if (-not $latest) { throw "No downloaded offsite backup found in $BackupRoot" }
    $BackupId = $latest.Name -replace '\.tar\.gz\.age$',''
} else {
    $latest = Get-Item -LiteralPath (Join-Path $BackupRoot ($BackupId + '.tar.gz.age'))
}
if ($BackupId -notmatch '^backup-\d{8}T\d{12}Z-[0-9a-f]{32}$') { throw 'Invalid backup ID.' }
$ciphertext = Join-Path $BackupRoot ($BackupId + '.tar.gz.age')
$index = $ciphertext + '.json'
if (-not (Test-Path -LiteralPath $index -PathType Leaf)) { throw 'Backup integrity index is missing.' }

$keyRoot = Join-Path $appRoot 'restore-drill'
New-Item -ItemType Directory -Force -Path $keyRoot | Out-Null
& icacls.exe $keyRoot /inheritance:r /grant:r "$($user):(OI)(CI)(F)" | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not restrict restore key directory.' }
$sshKey = Join-Path $keyRoot 'id_ed25519'
if (-not (Test-Path -LiteralPath $sshKey)) {
    $keyProcess = Start-Process -FilePath $sshKeygen -ArgumentList @(
        '-q','-t','ed25519','-N','""','-C',('finsentinel-restore-drill-' + $BackupId),'-f',$sshKey
    ) -PassThru -Wait -NoNewWindow
    if ($keyProcess.ExitCode -ne 0) { throw 'Could not generate one-time restore key.' }
}
$publicKey = Get-Content -LiteralPath ($sshKey + '.pub') -Raw
$fingerprint = (& $sshKeygen -lf ($sshKey + '.pub') | Out-String).Trim()
Write-Output "Backup ID: $BackupId"
Write-Output "One-time SSH key fingerprint: $fingerprint"
Write-Output 'Paste this public key into the ECS receiver installation command:'
Write-Output $publicKey.Trim()

if ($Send) {
    Push-Location $clientRoot
    try {
        & $python -m scripts.offsite_restore_transfer `
            --ciphertext $ciphertext --index $index --identity $AgeIdentity `
            --ssh-key $sshKey --known-hosts $KnownHosts --server $Server `
            --age-exe $ageExe --ssh-exe $sshExe
        if ($LASTEXITCODE -ne 0) { throw 'Offsite restore transfer failed.' }
        Remove-Item -LiteralPath $sshKey,($sshKey + '.pub') -Force
        Write-Output 'One-time local SSH key removed.'
    } finally {
        Pop-Location
    }
}
