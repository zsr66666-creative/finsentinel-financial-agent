param(
    [string]$Server = '120.24.108.60',
    [string]$PythonExe = 'python.exe',
    [string]$BackupRoot = "$env:USERPROFILE\FinSentinelBackups",
    [string]$AgeIdentity = "$env:USERPROFILE\finsentinel-age-key.txt",
    [string]$SshPrivateKey = "$env:USERPROFILE\.ssh\finsentinel-backup-pull",
    [string]$KnownHosts = "$env:LOCALAPPDATA\FinSentinel\ssh_known_hosts",
    [string]$DailyAt = '4:00AM'
)

$ErrorActionPreference = 'Stop'
$TaskName = 'FinSentinel-OffsitePull'
$AppRoot = Join-Path $env:LOCALAPPDATA 'FinSentinel'
$ClientRoot = Join-Path $AppRoot 'client'
$StatusPath = Join-Path $AppRoot 'pull-status.json'
$SourceRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\scripts'))
$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

function Assert-Command([string]$Name) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) { throw "Required command not found: $Name" }
    return $command.Source
}

function Protect-File([string]$Path) {
    & icacls.exe $Path /inheritance:r /grant:r "$($CurrentUser):(F)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not restrict file ACL: $Path" }
}

function Protect-Directory([string]$Path) {
    & icacls.exe $Path /inheritance:r /grant:r "$($CurrentUser):(OI)(CI)(F)" /T /C | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not restrict directory ACL: $Path" }
}

$parsedAddress = $null
if (-not [System.Net.IPAddress]::TryParse($Server, [ref]$parsedAddress) -or
    $parsedAddress.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
    throw 'Server must be an IPv4 address.'
}

$python = Assert-Command $PythonExe
$sftp = Assert-Command 'sftp.exe'
$sshKeygen = Assert-Command 'ssh-keygen.exe'
$age = Assert-Command 'age.exe'
$ageKeygen = Assert-Command 'age-keygen.exe'
$identity = [System.IO.Path]::GetFullPath($AgeIdentity)
$sshKey = [System.IO.Path]::GetFullPath($SshPrivateKey)
$knownHostsPath = [System.IO.Path]::GetFullPath($KnownHosts)
$backupPath = [System.IO.Path]::GetFullPath($BackupRoot)

if (-not (Test-Path -LiteralPath $identity -PathType Leaf)) { throw "Age identity not found: $identity" }
if (-not (Test-Path -LiteralPath $knownHostsPath -PathType Leaf)) {
    throw "Pinned SSH host key is missing: $knownHostsPath. Add the key copied from the ECS console after comparing its fingerprint."
}
if ((Get-Item -LiteralPath $knownHostsPath).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'The pinned known_hosts file must not be a reparse point.'
}
& $sshKeygen -F $Server -f $knownHostsPath *> $null
if ($LASTEXITCODE -ne 0) { throw "No pinned SSH host key found for $Server." }

$keyDirectory = Split-Path -Parent $sshKey
New-Item -ItemType Directory -Force -Path $keyDirectory | Out-Null
$publicKeyPath = "$sshKey.pub"
$hasPrivate = Test-Path -LiteralPath $sshKey -PathType Leaf
$hasPublic = Test-Path -LiteralPath $publicKeyPath -PathType Leaf
if ($hasPrivate -xor $hasPublic) { throw 'Only one half of the dedicated SSH key pair exists; refusing to replace it.' }
if (-not $hasPrivate) {
    & $sshKeygen -q -t ed25519 -N '' -C 'finsentinel-windows-backup-pull' -f $sshKey
    if ($LASTEXITCODE -ne 0) { throw 'Could not generate the dedicated SFTP key pair.' }
}

New-Item -ItemType Directory -Force -Path $AppRoot,$ClientRoot,$backupPath | Out-Null
Protect-File $identity
Protect-File $sshKey
Protect-Directory $backupPath
Protect-Directory $AppRoot

$scriptDestination = Join-Path $ClientRoot 'scripts'
New-Item -ItemType Directory -Force -Path $scriptDestination | Out-Null
foreach ($name in @('windows_offsite_pull.py','verify_offsite_archive.py')) {
    $source = Join-Path $SourceRoot $name
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Packaged client file missing: $source" }
    Copy-Item -LiteralPath $source -Destination (Join-Path $scriptDestination $name) -Force
}

$ageRecipient = (& $ageKeygen -y $identity).Trim()
if ($LASTEXITCODE -ne 0 -or $ageRecipient -notmatch '^age1[0-9a-z]{8,100}$') {
    throw 'Could not derive a valid public recipient from the age identity.'
}
$hostFingerprint = (& $sshKeygen -lf $knownHostsPath 2>$null | Out-String).Trim()
if (-not $hostFingerprint) { throw 'Could not read the pinned SSH host-key fingerprint.' }

$dailyTrigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $CurrentUser
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 60) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId $CurrentUser -LogonType Interactive -RunLevel Limited
$arguments = @(
    '-B', '-m', 'scripts.windows_offsite_pull',
    '--server', $Server,
    '--known-hosts', $knownHostsPath,
    '--ssh-key', $sshKey,
    '--age-identity', $identity,
    '--local-dir', $backupPath,
    '--status-path', $StatusPath,
    '--sftp-exe', $sftp
) | ForEach-Object { '"' + ([string]$_).Replace('"','\"') + '"' }
$action = New-ScheduledTaskAction -Execute $python -Argument ($arguments -join ' ') -WorkingDirectory $ClientRoot

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($dailyTrigger,$logonTrigger) `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Output "Task registered: $TaskName (daily at $DailyAt and at next logon after a missed run)."
Write-Output "Pinned SSH fingerprint: $hostFingerprint"
Write-Output "Age public recipient: $ageRecipient"
Write-Output "Dedicated SFTP public key to install on ECS:"
Get-Content -LiteralPath $publicKeyPath
Write-Output "Backup directory: $backupPath"
Write-Output "Status file: $StatusPath"
Write-Output "Task status: Get-ScheduledTaskInfo -TaskName $TaskName"
