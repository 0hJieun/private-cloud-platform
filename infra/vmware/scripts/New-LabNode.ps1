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

    [switch]$AddProviderAdapter,

    [string]$SourceVmx = 'C:\PrivateCloudLab\images\rocky9-base\rocky9-base.vmx',

    [string]$LabRoot = 'C:\PrivateCloudLab',

    [string]$ManagementNetwork = 'VMnet2',

    [string]$ProviderNetwork = 'VMnet8'
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

if (-not (Test-Path -LiteralPath $SourceVmx -PathType Leaf)) {
    throw "기반 VMX를 찾을 수 없습니다: $SourceVmx"
}

$runningVms = & $vmrun -T ws list
if ($runningVms -contains $SourceVmx) {
    throw '기반 이미지는 전원이 꺼진 상태여야 복제할 수 있습니다.'
}

$destinationDirectory = Join-Path $LabRoot $Name
$destinationVmx = Join-Path $destinationDirectory "$Name.vmx"
if (Test-Path -LiteralPath $destinationDirectory) {
    throw "대상 폴더가 이미 존재합니다. 덮어쓰지 않습니다: $destinationDirectory"
}

New-Item -ItemType Directory -Path $destinationDirectory | Out-Null

try {
    & $vmrun -T ws clone $SourceVmx $destinationVmx full -cloneName $Name
    if ($LASTEXITCODE -ne 0) {
        throw "VMware 복제에 실패했습니다. 종료 코드: $LASTEXITCODE"
    }

    $vmxLines = [System.Collections.Generic.List[string]]::new()
    foreach ($line in Get-Content -LiteralPath $destinationVmx) {
        [void]$vmxLines.Add($line)
    }

    Set-VmxValue -Lines $vmxLines -Key 'displayName' -Value $Name
    Set-VmxValue -Lines $vmxLines -Key 'numvcpus' -Value $Vcpus
    Set-VmxValue -Lines $vmxLines -Key 'cpuid.coresPerSocket' -Value $Vcpus
    Set-VmxValue -Lines $vmxLines -Key 'memsize' -Value $MemoryMB

    # compute 노드는 VMware 위에서 KVM을 실행하므로 nested virtualization이 필요하다.
    Set-VmxValue -Lines $vmxLines -Key 'vhv.enable' -Value 'TRUE'

    # 기반 이미지 생성에만 쓴 ISO/OEMDRV CD 장치는 복제 노드에서 비활성화한다.
    Set-VmxValue -Lines $vmxLines -Key 'sata0:0.present' -Value 'FALSE'
    Set-VmxValue -Lines $vmxLines -Key 'sata1:0.present' -Value 'FALSE'

    # 첫 번째 NIC는 control의 Ansible이 사용하는 관리망이다.
    Set-VmxValue -Lines $vmxLines -Key 'ethernet0.present' -Value 'TRUE'
    Set-VmxValue -Lines $vmxLines -Key 'ethernet0.connectionType' -Value 'custom'
    Set-VmxValue -Lines $vmxLines -Key 'ethernet0.vnet' -Value $ManagementNetwork
    Set-VmxValue -Lines $vmxLines -Key 'ethernet0.virtualDev' -Value 'vmxnet3'
    Set-VmxValue -Lines $vmxLines -Key 'ethernet0.startConnected' -Value 'TRUE'
    Set-VmxValue -Lines $vmxLines -Key 'ethernet0.addressType' -Value 'generated'

    if ($AddProviderAdapter) {
        # 두 번째 NIC는 OVS br-provider를 통해 내부 인스턴스에 제공할 uplink다.
        Set-VmxValue -Lines $vmxLines -Key 'ethernet1.present' -Value 'TRUE'
        Set-VmxValue -Lines $vmxLines -Key 'ethernet1.connectionType' -Value 'custom'
        Set-VmxValue -Lines $vmxLines -Key 'ethernet1.vnet' -Value $ProviderNetwork
        Set-VmxValue -Lines $vmxLines -Key 'ethernet1.virtualDev' -Value 'vmxnet3'
        Set-VmxValue -Lines $vmxLines -Key 'ethernet1.startConnected' -Value 'TRUE'
        Set-VmxValue -Lines $vmxLines -Key 'ethernet1.addressType' -Value 'generated'
    }

    Set-Content -LiteralPath $destinationVmx -Value $vmxLines -Encoding ascii
}
catch {
    throw "복제본을 남긴 채 중단했습니다. 원인을 확인한 뒤 수동으로 정리하세요: $($_.Exception.Message)"
}

Write-Host "생성 완료: $destinationVmx"
Write-Host 'VMware Workstation에서 File > Open으로 이 VMX를 열어 설정을 확인할 수 있습니다.'
Write-Host '이 스크립트는 VM을 부팅하지 않습니다.'
