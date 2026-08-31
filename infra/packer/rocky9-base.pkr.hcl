packer {
  required_plugins {
    vmware = {
      source  = "github.com/vmware/vmware"
      version = "~> 2.1"
    }
  }
}

variable "iso_path" {
  type        = string
  description = "Rocky Linux Minimal ISO의 Windows 절대 경로"
}

variable "iso_checksum" {
  type        = string
  description = "sha256:<해시값> 형식의 ISO SHA-256 검증값"
}

variable "output_directory" {
  type        = string
  description = "기본 VMware 이미지가 생성될 로컬 경로"
  default     = "C:/PrivateCloudLab/images/rocky9-base"
}

variable "build_ip" {
  type        = string
  description = "기본 이미지 생성 과정에서만 사용하는 VMnet2 임시 주소"
  default     = "172.16.2.100"
}

variable "build_netmask" {
  type    = string
  default = "255.255.255.0"
}

variable "build_hostname" {
  type    = string
  default = "packer-build"
}

variable "ssh_private_key_path" {
  type        = string
  description = "이미지 생성에만 사용하는 Packer SSH 개인키의 로컬 경로"
  default     = "C:/Users/user/.ssh/private-cloud-packer-build"
}

variable "ssh_public_key_path" {
  type        = string
  description = "이미지 생성에만 사용하는 Packer SSH 공개키의 로컬 경로"
  default     = "C:/Users/user/.ssh/private-cloud-packer-build.pub"
}

variable "ansible_public_key_path" {
  type        = string
  description = "control의 Ansible 전용 SSH 공개키 경로"
  default     = "C:/Users/user/.ssh/private-cloud-ansible.pub"
}

source "vmware-iso" "rocky9_base" {
  iso_url      = var.iso_path
  iso_checksum = var.iso_checksum

  vm_name          = "rocky9-base"
  display_name     = "rocky9-base"
  output_directory = var.output_directory
  guest_os_type    = "rockylinux-64"
  firmware         = "efi"

  cpus      = 1
  cores     = 1
  memory    = 2048
  disk_size = 20480
  # VMware의 growable(씬 프로비저닝) 가상 디스크 형식
  disk_type_id       = "1"
  cdrom_adapter_type = "sata"
  sound              = false
  usb                = false

  # 플러그인은 custom VMnet의 DHCP 설정 파일을 전제로 호스트 IP를 감지한다.
  # VMnet2 DHCP는 의도적으로 비활성화했으므로 감지 단계만 bridged로 통과시킨다.
  # 실제 생성 VM의 NIC는 아래 vmx_data로 VMnet2에 고정한다.
  network              = "bridged"
  network_adapter_type = "vmxnet3"
  vmx_data = {
    "ethernet0.connectionType" = "custom"
    "ethernet0.vnet"           = "vmnet2"
  }

  # Rocky/RHEL 설치기는 OEMDRV 레이블 장치의 /ks.cfg를 자동으로 탐색한다.
  # HTTP 서버와 설치 초기 네트워크 설정에 의존하지 않기 위한 보조 CD다.
  cd_content = {
    "ks.cfg" = templatefile("${abspath(path.root)}/ks.cfg.pkrtpl", {
      build_ip               = var.build_ip
      build_netmask          = var.build_netmask
      build_hostname         = var.build_hostname
      packer_authorized_key  = trimspace(file(var.ssh_public_key_path))
      ansible_authorized_key = trimspace(file(var.ansible_public_key_path))
    })
  }
  cd_label = "OEMDRV"

  # OEMDRV/ks.cfg는 Rocky 설치기가 기본 부팅 항목에서 자동으로 탐색한다.
  # GRUB에 키를 입력하지 않아 Workstation 콘솔 포커스나 키 시퀀스에 의존하지 않는다.

  communicator         = "ssh"
  ssh_host             = var.build_ip
  ssh_username         = "packer"
  ssh_private_key_file = var.ssh_private_key_path
  ssh_timeout          = "20m"

  # Packer 종료 후, 복제본의 첫 부팅에서 systemd 서비스가 Packer 계정을 제거한다.
  shutdown_command = "sudo /usr/local/sbin/cleanup-template && sudo systemctl poweroff"
  shutdown_timeout = "5m"
}

build {
  name    = "rocky9-base"
  sources = ["source.vmware-iso.rocky9_base"]

  provisioner "file" {
    source      = "${abspath(path.root)}/scripts/cleanup-template.sh"
    destination = "/tmp/cleanup-template.sh"
  }

  provisioner "shell" {
    inline = [
      "sudo install -o root -g root -m 0755 /tmp/cleanup-template.sh /usr/local/sbin/cleanup-template",
      "sudo /usr/sbin/sshd -t",
      "sudo systemctl is-enabled sshd"
    ]
  }
}
