#Requires -Version 7.0
<#
현재 Windows 사용자에게 실습 CA를 신뢰시키고, 기존 hosts 내용은 보존하며
프로젝트의 두 웹 이름만 등록한다. 개인키와 LAN 포트 전달은 취급하지 않는다.
#>
[CmdletBinding()]
param(
    [string]$CertificatePath,
    [string]$ExpectedSha256,
    [ValidatePattern('^172\.16\.8\.10$')]
    [string]$Address = '172.16.8.10',
    [switch]$HostsOnly
)

$ErrorActionPreference = 'Stop'
$hostsPath = Join-Path $env:SystemRoot 'System32/drivers/etc/hosts'
$beginMarker = '# BEGIN PRIVATE CLOUD WEB'
$endMarker = '# END PRIVATE CLOUD WEB'
$managedBlock = "$beginMarker`r`n$Address cloud.lab.test grafana.lab.test`r`n$endMarker"
$isAdmin = [Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $HostsOnly) {
    if (-not $CertificatePath -or $ExpectedSha256 -notmatch '^[A-Fa-f0-9]{64}$') {
        throw 'CA 공개 인증서 경로와 SSH로 확인한 SHA-256 지문을 지정하세요.'
    }
    $certPath = (Resolve-Path -LiteralPath $CertificatePath).Path
    $cert = [Security.Cryptography.X509Certificates.X509Certificate2]::new($certPath)
    if ($cert.HasPrivateKey -or $cert.GetCertHashString('SHA256') -ne $ExpectedSha256) {
        throw 'CA 공개 인증서의 지문이 일치하지 않거나 개인키가 포함되어 있습니다.'
    }
    if ($cert.Subject -ne $cert.Issuer -or $cert.Subject -notmatch 'CN=Private Cloud Lab Root CA') {
        throw '예상한 Private Cloud Lab Root CA가 아닙니다.'
    }
    if ($cert.NotAfter -le (Get-Date) -or $cert.NotBefore -gt (Get-Date)) {
        throw 'CA 인증서의 유효기간을 확인하세요.'
    }
    $store = [Security.Cryptography.X509Certificates.X509Store]::new('Root', 'CurrentUser')
    try {
        $store.Open('ReadWrite')
        if (-not ($store.Certificates | Where-Object Thumbprint -eq $cert.Thumbprint)) {
            $store.Add($cert)
        }
    } finally {
        $store.Close()
    }
    Write-Host '현재 Windows 사용자에게 CA 공개 인증서를 등록했습니다.'
}

$original = [IO.File]::ReadAllText($hostsPath)
$pattern = '(?ms)^' + [regex]::Escape($beginMarker) + '\r?\n.*?^' + [regex]::Escape($endMarker) + '\r?\n?'
$outsideBlock = [regex]::Replace($original, $pattern, '')
if ($outsideBlock -match '(?m)^\s*[^#\r\n]+\s(?:[^#\r\n]*\s)?(?:cloud|grafana)\.lab\.test(?:\s|$)') {
    throw '관리 블록 밖에 같은 웹 이름이 있습니다. 기존 매핑을 먼저 확인하세요.'
}
$updated = $outsideBlock.TrimEnd("`r", "`n") + "`r`n`r`n" + $managedBlock + "`r`n"
if ($original -ne $updated) {
    if (-not $isAdmin) {
        Write-Host 'hosts 등록을 위해 Windows 관리자 승인 창이 표시됩니다.'
        $child = Start-Process -FilePath (Join-Path $PSHOME 'pwsh.exe') -Verb RunAs -WindowStyle Hidden -PassThru -Wait -ArgumentList @(
            '-NoProfile', '-File', "`"$PSCommandPath`"", '-HostsOnly', '-Address', $Address
        )
        if ($child.ExitCode -ne 0) { throw '관리자 권한 hosts 등록이 완료되지 않았습니다.' }
        if (-not ([IO.File]::ReadAllText($hostsPath).Contains($managedBlock))) {
            throw 'hosts 등록 결과가 예상과 다릅니다.'
        }
    } else {
        $backupPath = "$hostsPath.private-cloud-$(Get-Date -Format yyyyMMdd-HHmmss).bak"
        Copy-Item -LiteralPath $hostsPath -Destination $backupPath -ErrorAction Stop
        [IO.File]::WriteAllText($hostsPath, $updated, [Text.UTF8Encoding]::new($false))
        Write-Host "기존 hosts 백업: $backupPath"
    }
}
Write-Host '완료: https://cloud.lab.test / https://grafana.lab.test'
