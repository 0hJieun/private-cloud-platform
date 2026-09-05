# `cloudctl` 운영 CLI

`cloudctl`은 portal·API를 만들기 전 scheduler와 Ansible 프로비저너를 독립 검증하기 위해 만든 운영자용 진단 CLI다. 현재 표준 VM 생성·삭제 진입점은 portal/API이며, `cloudctl` direct 실행은 MariaDB operation·event·runtime inventory lifecycle을 우회할 수 있으므로 일상 운영에는 사용하지 않는다.

```text
cloudctl create
  → scheduler: compute 상태와 예약량 비교
  → Ansible: 선택된 compute에 disk·seed·domain 생성
  → DHCP: provider IP 할당
```

## 코드 독해·진단 명령어

control에서 프로젝트 루트로 이동한 뒤 실행한다.

```bash
cd ~/private-cloud-platform

# 생성 전 배치 대상만 확인하는 진단 경로다.
python3 control-plane/scheduler/cloudctl.py plan \
  --name app01 --vcpus 1 --memory-mb 1024 --disk-gb 10

# 이 direct 생성은 portal DB lifecycle을 우회하므로 일반 운영에서 사용하지 않는다.
python3 control-plane/scheduler/cloudctl.py create \
  --name app01 --vcpus 1 --memory-mb 1024 --disk-gb 10

# compute별 instance 이름, 상태, 예약 자원을 출력한다.
python3 control-plane/scheduler/cloudctl.py list

# guest OS를 정상 종료한 다음 libvirt domain, qcow2 overlay, cloud-init seed를 삭제한다.
python3 control-plane/scheduler/cloudctl.py delete --name app01
```

`delete`는 강제 종료하지 않는다. 60초 동안 정상 종료를 기다리며, 종료되지 않으면 실패로 남긴다. 이때 운영자가 console·로그를 확인하고 별도 강제 종료 여부를 판단한다.

## 현재 역할 분리

| 구성 요소 | 책임 |
|---|---|
| portal/API + worker | 표준 요청 생성, DB lifecycle, 비동기 실행 |
| `cloudctl` | 초기 검증·코드 독해용 진단 CLI |
| `scheduler.py` | compute 상태 수집과 대상 선택 |
| `provision-instance.yml` | 이미지·cloud-init·libvirt의 desired state 적용 |
| `destroy-instance.yml` | 정상 종료 후 domain·인스턴스 전용 데이터를 안전하게 정리 |

현재 관리자 웹/API가 scheduler·provisioner를 호출한다. `cloudctl`은 scheduler와 Ansible의 경계를 이해하기 위한 보조 도구로 남긴다.
