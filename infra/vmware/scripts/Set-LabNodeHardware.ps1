[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[a-z][a-z0-9-]{2,20}$')]
    [string]$Name,

    [Parameter(Mandatory)]
    [ValidateRange(1, 16)]
    [int]$Vcpus,

    [Parameter(Mandatory)]
    [ValidateRange(1024, 16384)]
    [int]$MemoryMB,

    [string]$LabRoot = 'C:\PrivateCloudLab'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Set-VmxValue {
    param(
        [Parameter(Mandatory)]
        [System.Collections.Generic.List[string]]$Lines,

        [Parameter(Mandatory)]
        [string]$Key,

        [Parameter(Mandatory)]
        [string]$Value
    )

    $pattern = '^\s*' + [regex]::Escape($Key) + '\s*=\s*".*"\s*$'
    $replacement = "$Key = `"$Value`""

    for ($index = 0; $index -lt $Lines.Count; $index++) {
        if ($Lines[$index] -match $pattern) {
            $Lines[$index] = $replacement
            return
        }
    }

    [void]$Lines.Add($replacement)
}

$vmrun = 'C:\Program Files\VMware\VMware Workstation\vmrun.exe'
if (-not (Test-Path -LiteralPath $vmrun -PathType Leaf)) {
    throw "vmrun을 찾을 수 없습니다: $vmrun"
}

$vmxPath = Join-Path (Join-Path $LabRoot $Name) "$Name.vmx"
if (-not (Test-Path -LiteralPath $vmxPath -PathType Leaf)) {
    throw "대상 VMX를 찾을 수 없습니다: $vmxPath"
}

# 실행 중인 VMX는 수정하지 않는다. 종료 후에만 하드웨어 값을 변경한다.
$runningVms = & $vmrun -T ws list
if ($runningVms -contains $vmxPath) {
    throw "VM이 실행 중입니다. 정상 종료 후 다시 실행하세요: $vmxPath"
}

$vmxLines = [System.Collections.Generic.List[string]]::new()
foreach ($line in Get-Content -LiteralPath $vmxPath) {
    [void]$vmxLines.Add($line)
}

Set-VmxValue -Lines $vmxLines -Key 'numvcpus' -Value $Vcpus
Set-VmxValue -Lines $vmxLines -Key 'cpuid.coresPerSocket' -Value $Vcpus
Set-VmxValue -Lines $vmxLines -Key 'memsize' -Value $MemoryMB

Set-Content -LiteralPath $vmxPath -Value $vmxLines -Encoding ascii

Write-Host "변경 완료: $Name"
Write-Host "CPU: $Vcpus vCPU, 메모리: $MemoryMB MB"
Write-Host 'VMware Workstation에서 전원을 켠 뒤 게스트 OS 상태를 확인하세요.'
