# `cloudctl` 운영 CLI

`cloudctl`은 control 노드 운영자가 inner VM을 다루는 표준 진입점이다. 사용자는 Ansible playbook, libvirt, 공유 디스크 경로를 직접 조합하지 않는다. CLI는 scheduler에게 배치를 맡기고, scheduler는 검증된 Ansible 프로비저너를 호출한다.

```text
cloudctl create
  → scheduler: compute 상태와 예약량 비교
  → Ansible: 선택된 compute에 disk·seed·domain 생성
  → DHCP: provider IP 할당
```

## 명령어

control에서 프로젝트 루트로 이동한 뒤 실행한다.

```bash
cd ~/private-cloud-platform

# 생성 전 배치 대상만 확인한다.
python3 control-plane/scheduler/cloudctl.py plan \
  --name app01 --vcpus 1 --memory-mb 1024 --disk-gb 10

# scheduler가 선택한 compute에 실제 생성한다.
python3 control-plane/scheduler/cloudctl.py create \
  --name app01 --vcpus 1 --memory-mb 1024 --disk-gb 10

# compute별 instance 이름, 상태, 예약 자원을 출력한다.
python3 control-plane/scheduler/cloudctl.py list

# guest OS를 정상 종료한 다음 libvirt domain, qcow2 overlay, cloud-init seed를 삭제한다.
python3 control-plane/scheduler/cloudctl.py delete --name app01
```

`delete`는 강제 종료하지 않는다. 60초 동안 정상 종료를 기다리며, 종료되지 않으면 실패로 남긴다. 이때 운영자가 console·로그를 확인하고 별도 강제 종료 여부를 판단한다.

## 역할 분리

| 구성 요소 | 책임 |
|---|---|
| `cloudctl` | 운영자용 명령 형식과 lifecycle 명령 제공 |
| `scheduler.py` | compute 상태 수집과 대상 선택 |
| `provision-instance.yml` | 이미지·cloud-init·libvirt의 desired state 적용 |
| `destroy-instance.yml` | 정상 종료 후 domain·인스턴스 전용 데이터를 안전하게 정리 |

향후 관리자 웹/API는 `cloudctl`의 로직을 서비스 계층으로 옮겨 같은 scheduler·provisioner를 호출한다. 이 단계에서는 control 한 대의 운영 CLI로 전체 인스턴스 lifecycle을 검증한다.
