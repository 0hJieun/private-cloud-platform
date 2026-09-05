# Inner VM Ansible 자동 편입

## 목적

이 기능은 portal의 VM 생성 경험과 control의 구성 관리 경험을 연결한다. 사용자는 portal에서
자기 공개키로 VM에 접속하고, control worker는 DHCP IP를 확인한 뒤 새 VM을 Ansible의
runtime `instances` 그룹에 자동 등록한다. 따라서 운영자는 생성 완료 뒤 다음처럼 post-provision
검증이나 공통 설정 playbook을 실행할 수 있다.

```bash
cd ~/private-cloud-platform/automation/ansible
ansible-inventory --graph
ansible-playbook playbooks/verify-managed-instances.yml
```

## 키와 inventory 경계

| 항목 | control의 실제 경로 | 용도 | Git 저장 여부 |
|---|---|---|---|
| outer 인프라 자동화 개인키 | `/home/user1/.ssh/private-cloud-ansible` | control → compute/storage SSH | 저장 안 함 |
| inner VM automation 개인키 | `/home/user1/.ssh/private-cloud-instance-automation` | control → 새 inner VM SSH | 저장 안 함 |
| inner VM automation 공개키 | `/home/user1/.ssh/private-cloud-instance-automation.pub` | 새 VM cloud-init `authorized_keys` 주입 | 저장 안 함 |
| outer inventory | `automation/ansible/inventory/hosts.yml` | control/compute/storage 고정 호스트 | Git 관리 |
| dynamic inventory adapter | `automation/ansible/inventory/instances.py` | runtime JSON을 `[instances]`로 반환 | Git 관리 |
| runtime instance 상태 | `/home/user1/.local/share/private-cloud/ansible/instances.json` | ACTIVE VM IP·Ansible hostvars | Git 저장 안 함 |
| outer SSH 별칭 | `/home/user1/.ssh/config.d/private-cloud-outer.conf` | control → compute/storage의 `ssh compute1` 등 | Ansible 관리 |
| inner VM SSH 별칭 | `/home/user1/.ssh/config.d/private-cloud-instances.conf` | control → ACTIVE VM의 `ssh vm02` 등 | worker 관리 |

`ansible.cfg`는 `hosts.yml`과 `instances.py`를 함께 inventory source로 읽는다. Python adapter는
runtime JSON이 없거나 손상되어도 빈 `instances` 그룹을 반환하므로, outer 인프라 playbook을 막지 않는다.
OpenSSH는 Ansible inventory를 읽지 않으므로 별칭 파일도 별도로 필요하다. `~/.ssh/config`의
`Include /home/user1/.ssh/config.d/*.conf`은 한 번만 Ansible이 등록한다. 이후 outer 노드는
고정 inventory에서, inner VM은 worker가 runtime inventory와 같은 시점에 생성·삭제한다.

control에서 사용하는 예시는 다음과 같다.

```bash
# 고정 outer 노드
ssh compute1
ssh storage2

# portal에서 생성되어 ACTIVE가 된 inner VM
ssh vm02

# 여러 inner VM에 같은 명령을 적용할 때는 SSH 반복보다 Ansible을 사용한다.
ansible instances -m command -a 'hostnamectl --static'
```

## 생성·삭제 흐름

```text
portal 생성 요청
  → worker가 compute 선택
  → Ansible provisioner가 owner key + automation public key를 cloud-init seed에 작성
  → libvirt VM 부팅
  → control DHCP lease에서 provider IP 확인
  → instances.automation_enrolled=true, ACTIVE
  → worker가 instances.json과 private-cloud-instances.conf를 원자적으로 교체
  → ansible instances -m ping 및 ssh <instance-name> 가능

portal 삭제 요청
  → Ansible이 libvirt domain·overlay·seed 제거
  → DB soft delete
  → worker가 instances.json·SSH 별칭 파일을 다시 생성해 해당 호스트 제거
```

## 안전 경계와 한계

- 기존 `vm01`, `monitor01`처럼 automation 기능 배포 전에 만든 VM은 새 키가 없으므로 자동 등록하지 않는다.
  이들은 재생성하지 않는 한 owner key만으로 접속한다.
- `clouduser`는 이 실습에서 passwordless sudo를 갖는다. 그러므로 owner key와 control automation key
  모두 해당 VM 안에서는 높은 권한을 갖는다. 실서비스 multi-tenant 환경이라면 tenant의 OS 관리 권한 정책,
  별도 agent·consent, SSH host CA, credential rotation을 별도로 설계해야 한다.
- lab은 DHCP IP 재사용을 위해 control 전용 known-hosts 파일에서 삭제된 IP fingerprint를 정리하고
  `StrictHostKeyChecking=accept-new`으로 첫 fingerprint를 기록한다. 운영 환경에서는 TOFU 대신 SSH host
  certificate 또는 조직 CA로 host identity를 검증한다.
