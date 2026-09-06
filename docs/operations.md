# 설치·운영

## 실행 환경과 구성 순서

Windows의 VMware Workstation·PowerShell·Packer와 Rocky Linux 9 기반 노드를 사용합니다. control에는 Git·Ansible과 SSH·sudo 권한이 필요합니다.
현재 API 배포는 Rocky 9의 Python 3.9를 기준으로 구성되어 있습니다.

다른 PC에 재현하려면 [노드 사양](../infra/vmware/lab.yml), [인벤토리](../automation/ansible/inventory/hosts.yml), [웹 설정](../automation/ansible/inventory/group_vars/control_nodes.yml)의 경로·주소부터 확인합니다.
`lab.yml`은 사양 명세이며 PowerShell 스크립트가 이 파일을 읽어 전체 환경을 자동 생성하는 것은 아닙니다.

| 순서 | 실행 위치 | 사용할 코드 |
|---:|---|---|
| 1 | Windows | `infra/packer/rocky9-base.pkr.hcl`로 기반 이미지 생성. ISO 경로·SHA-256·빌드용 키·관리 공개키 지정 |
| 2 | Windows | `New-LabNode.ps1`로 노드 복제. compute는 중첩 가상화, storage는 데이터 디스크 준비 |
| 3 | control | `bootstrap-node.yml`로 복제 노드를 한 대씩 고정 이름·관리 IP로 초기화 |
| 4 | control | compute에 `bootstrap-provider-network.yml` → `configure-compute-runtime.yml` → `configure-ovs-provider-bridge.yml` |
| 5 | control | storage에 `configure-storage-provider-network.yml` → `configure-gluster-storage.yml` → `configure-gluster-cluster.yml` |
| 6 | control | `configure-gluster-clients.yml`로 control·compute 마운트 → `prepare-cloud-image.yml` → `configure-control-dhcp.yml` |
| 7 | control | `configure-control-api.yml` → `configure-ubuntu-image.yml` → `configure-monitoring.yml` |
| 공통 | control | `bootstrap-control.yml`의 SSH 정책과 `configure-time-sync.yml`의 시각 동기화 적용 |

표의 플레이북은 모두 `automation/ansible/playbooks/` 아래에 있습니다. 초기 control 설치·VMware 가상 네트워크·SSH 신뢰 설정은 먼저 준비해야 합니다.
복제 직후 주소 `172.16.2.100`은 한 대씩만 사용합니다. 초기화 주소에는 `/24`까지 전달합니다.
스토리지 구성은 빈 데이터 디스크에 파일시스템을 생성하므로 장치·용량을 확인한 뒤 실행해야 합니다.
SSH 비밀번호 인증을 끄기 전에는 별도 터미널에서 공개키 접속을 확인합니다.

## 기존 환경에 코드 배포

control의 Git 작업본과 실제 서비스 실행 위치는 다릅니다. `git pull`만으로 실행 중인 서비스가 바뀌지는 않습니다.

```bash
cd ~/private-cloud-platform
git pull --ff-only
cd automation/ansible

# API·웹·작업 처리기 코드와 HTTPS 설정 배포
ansible-playbook --ask-become-pass --limit control playbooks/configure-control-api.yml

# control의 모니터링 설정·알림·대시보드 배포
ansible-playbook --ask-become-pass --limit control playbooks/configure-monitoring.yml
```

모니터링 최초 구성이나 기반 노드 exporter 변경 때는 두 번째 명령의 `--limit control`을 빼고 실행합니다.
플랫폼이 관리하는 VM의 생성·삭제는 포털/API를 사용합니다. `cloudctl.py`와 개별 생성·삭제 플레이북의 직접 실행은 DB 작업 경로를 우회하므로 별도 개발·진단용입니다.

## HTTPS 접속

- 포털: `https://cloud.lab.test` — 포털 관리자·사용자 계정.
- Grafana: `https://grafana.lab.test` — 운영자 전용 별도 계정. 포털과 통합 로그인하지 않습니다.
- 입구: Nginx `172.16.8.10:443`, 허용 클라이언트는 현재 Windows 호스트 `172.16.8.1/32`입니다.
- 기존 `172.16.2.10:8080`·`:3000` 직접 접속은 사용하지 않습니다.

control의 CA 공개 인증서 `/etc/pki/ca-trust/source/anchors/private-cloud-lab.crt`를 SSH/SCP로 Windows에 전달하고, 지문을 대조한 뒤 등록합니다.

```powershell
.\infra\vmware\scripts\Setup-LabWebClient.ps1 -CertificatePath '<CA 공개 인증서 경로>' -ExpectedSha256 '<SSH로 확인한 SHA-256 지문>'
```

스크립트는 현재 사용자 인증서 신뢰와 Windows hosts의 프로젝트 항목을 등록합니다. hosts 수정에는 관리자 승인이 필요할 수 있습니다.
인터넷 공개·LAN 포트 전달을 구성하지 않으므로 다른 PC에 hosts만 복사해도 접속되는 구조는 아닙니다. Slack 대시보드 링크도 해당 접속 환경이 필요합니다.
서버 인증서는 1년 유효하며 만료 30일 이내에 API 구성 플레이북을 재실행하면 갱신합니다. 정기 자동 갱신 작업은 없습니다.

## 파일과 서비스 위치

| 위치 | 용도 |
|---|---|
| `/home/user1/private-cloud-platform` | Git 작업본 |
| `/opt/private-cloud/release` | Ansible이 동기화하는 실제 API·작업 처리기 실행 코드 |
| `/etc/private-cloud/api.env` | DB 접속·세션·내부 수집 인증 설정 |
| `/etc/private-cloud/alertmanager.env` | Slack webhook 비밀값. root 전용 파일 |
| `/var/lib/private-cloud/volumes` | GlusterFS 원본 이미지·VM 디스크 공유 경로 |
| `~/.ssh/config.d/private-cloud-outer.conf` | Ansible이 관리하는 기반 노드 SSH 별칭 |
| `~/.ssh/config.d/private-cloud-instances.conf` | 작업 처리기가 생성하는 사용자 VM SSH 별칭 |
| `~/.local/share/private-cloud/ansible/instances.json` | 동적 `[instances]` 인벤토리 원본 |
| `~/.ssh/private-cloud-ansible` / `private-cloud-instance-automation` | 기반 노드용 / 사용자 VM 관리용 개인키 |

`~`는 control의 `user1` 홈입니다. 개인키·환경 파일·CA 개인키·서버 개인키는 Git과 캡처에 포함하지 않습니다.
자동 생성된 접속 파일은 직접 편집하지 않습니다. 생성·삭제 결과는 DB에서 갱신되고 관련 파일에 반영됩니다.

## 점검 명령

control에서 실행합니다. `ssh <VM이름>`의 이름은 현재 생성된 VM으로 바꿉니다.

```bash
systemctl is-active private-cloud-api private-cloud-worker mariadb nginx
curl --fail http://127.0.0.1:8000/health
ssh compute1 'sudo -n virsh list --all'
ssh <VM이름>

cd ~/private-cloud-platform/automation/ansible
ansible-inventory --graph
ansible-playbook playbooks/verify-managed-instances.yml
```

마지막 명령은 자동 편입된 VM의 SSH·Ansible 접근을 검사합니다. 목록을 추가하는 명령이 아니며 생성 후 매번 실행해야 하는 절차도 아닙니다.

## 모니터링과 알림

기반 노드는 고정 대상, 새 VM은 자동 설치된 node exporter와 API의 동적 대상 목록으로 수집합니다.
일반 사용자는 포털에서 자기 지표만 보고, 운영자는 Grafana에서 전체 노드·VM을 선택해 분석합니다. node exporter는 자원·파일시스템 지표를 수집하며 libvirt·GlusterFS 상태 전체를 진단하는 도구는 아닙니다.

| 알림 | 조건 | 점검 대상 |
|---|---|---|
| `ComputeNodeDown` | compute 수집 실패 30초 지속 | 노드 연결과 해당 노드의 VM |
| `StorageNodeDown` | storage 수집 실패 30초 지속 | 노드 연결, 복제본·스토리지 접근 |
| `ManagedInstanceExporterDown` | VM 수집 실패 30초 지속 | VM·네트워크·방화벽·exporter |
| `GlusterBrickCapacityHigh` | 데이터 파일시스템 사용률 85% 초과 10분 지속 | 원본 이미지와 VM 디스크 용량 |

수집·규칙 평가는 10초, 응답 대기는 최대 5초입니다. Alertmanager의 첫 전송 대기는 5초, 그룹 변경·복구 확인 주기는 15초, 같은 장애 반복 알림은 4시간 간격입니다.
장애 알림은 약 40–60초, exporter 응답 복구 후 알림은 약 10–30초를 예상하지만 네트워크·Slack 재시도와 VM 부팅 시간에 따라 달라집니다.
Slack webhook을 설정하지 않으면 외부 알림은 전송하지 않습니다. 수집 실패와 실제 VM 전원 상태는 구별해야 합니다.

## 기동·종료와 공유 스토리지

- 기동: **storage → control → compute** 순서로 진행하고 공유 볼륨 마운트를 확인한 뒤 VM 요청을 받습니다.
- 종료: 내부 VM을 정상 종료한 뒤 **compute → control → storage** 순서로 종료합니다. 평상시 강제 전원 차단은 사용하지 않습니다.
- 현재 마운트는 `/etc/fstab`의 `_netdev,backupvolfile-server=...` 방식입니다. 경로 접근 시 자동 재시도하는 systemd automount 구성은 아닙니다.
- 스토리지보다 먼저 부팅해 마운트가 실패했다면, 스토리지 정상화를 확인하고 해당 control·compute에서 `sudo mount /var/lib/private-cloud/volumes`로 다시 마운트합니다.

```bash
findmnt -T /var/lib/private-cloud/volumes
ssh storage1 'sudo -n gluster peer status'
ssh storage1 'sudo -n gluster volume status instance-volumes'
ssh storage1 'sudo -n gluster volume heal instance-volumes info summary'
```

GlusterFS는 두 데이터 노드의 복제 구성입니다. `backupvolfile-server`는 마운트 설정을 받을 대체 서버이지 별도 데이터 백업이나 arbiter가 아닙니다.
한쪽 노드 복구 후에는 연결·볼륨·동기화 상태를 함께 확인합니다. 네트워크 분리 시 서로 다른 쓰기가 발생하는 split-brain까지 막는 완전한 고가용성 구성을 주장하지 않습니다.
compute를 다시 켜서 같은 호스트의 VM이 재시작하는 복구와, 다른 호스트로 자동 이동하는 장애 조치는 별개의 기능입니다.
