# 아키텍처

## 계층과 역할

- **기반 VM:** VMware Workstation의 control·compute1·compute2·storage1·storage2. Packer 이미지와 PowerShell 스크립트로 생성하고 Ansible로 구성합니다.
- **사용자 VM:** compute 안에서 libvirt/KVM으로 실행합니다. Rocky Linux 9와 Ubuntu 24.04 클라우드 이미지를 지원합니다.
- **제어 서비스:** control의 Nginx·FastAPI·MariaDB·작업 처리기가 요청과 실행 결과를 연결합니다. 포털은 별도 프런트엔드 빌드 없이 정적 HTML·CSS·JavaScript로 제공합니다.

## 생성·삭제 처리

```text
웹 생성 폼 → API 권한·이름·자원 검사
                  ↓
          MariaDB에 VM·작업·이력 기록 → HTTP 202 응답
                  ↓
          단일 작업 처리기가 대기 작업 선택
                  ↓
          스케줄러가 compute 조회·선정
                  ↓
          Ansible → qcow2 변경분 디스크·cloud-init → libvirt VM 생성
                  ↓
          DHCP 임대에서 MAC에 해당하는 IP 확인
                  ↓
          VM 상태·SSH 별칭·Ansible 인벤토리 갱신
```

API는 HTTP 요청 안에서 Ansible 실행이 끝날 때까지 기다리지 않습니다. 작업 상태와 오류는 DB에 남고 웹은 이를 주기적으로 조회합니다.
삭제도 같은 작업 경로를 사용하며, 대상 이름을 서버에서 재확인한 뒤 정상 종료·VM 정의·관련 디스크 제거를 진행합니다.

```text
REQUESTED → SCHEDULING → PROVISIONING → WAITING_FOR_IP → ACTIVE
ACTIVE → DELETE_REQUESTED → DELETING → DELETED
생성·삭제 실행 실패 → ERROR / 작업 FAILED
```

`ACTIVE`는 생성과 IP 확인의 결과입니다. 현재 접근 가능 여부는 Prometheus 관측값으로 별도 계산하므로, 호스트 장애를 생성 이력에 덮어쓰지 않습니다.

## 배치 판단

[스케줄러](../control-plane/scheduler/scheduler.py)는 Ansible 인벤토리에서 compute를 찾고 SSH로 실제 libvirt 정의와 호스트 자원을 조회합니다.

1. SSH·libvirt 조회에 실패한 노드는 신규 배치 후보에서 제외합니다.
2. 예약 vCPU·메모리 여유가 요청량 이상이고, 실제 가용 메모리가 요청량보다 최소 512MB 많아야 합니다.
3. 후보를 **정의된 VM 수 → CPU 사용률 → 예약 메모리 → 예약 vCPU → 노드 이름** 순으로 비교합니다.

꺼진 VM도 다시 켜질 수 있으므로 libvirt에 정의가 남아 있으면 예약 자원으로 계산합니다.
웹의 사전 검사는 사용자 안내이며 최종 배치는 작업 실행 시 다시 확인합니다. [노드별 배치 한도](../automation/ansible/inventory/hosts.yml)와 호스트 사양은 구분합니다.
DB의 노드·자원 표시는 운영 화면용이며, 현재 스케줄러의 최종 판단 기준은 인벤토리와 SSH 조회 결과입니다.

## 네트워크와 웹 입구

| 경로 | 역할 |
|---|---|
| VMnet2 · `172.16.2.0/24` | control에서 기반 노드 SSH·Ansible 관리, 기반 노드 지표 수집 |
| VMnet8 · `172.16.8.0/24` | 사용자 VM 통신, 인터넷 경로, GlusterFS와 HTTPS 입구 |
| control DHCP · `ens192` | 사용자 VM에 `172.16.8.151–239` 할당. 고정 노드 주소는 풀 밖에 배치 |
| compute의 `br-provider` | OVS 가상 스위치. 물리 측 NIC `ens192`와 사용자 VM을 같은 L2 네트워크로 연결 |
| VMware NAT · `172.16.8.2` | 사용자 VM과 기반 노드의 외부 통신 게이트웨이 |

VMware DHCP는 VMnet2에서 사용하지 않으며, VMnet8에서도 control DHCP와 충돌하지 않도록 비활성화합니다.
OVS는 IP를 할당하지 않습니다. compute 자신의 provider IP는 `ens192`가 아니라 OVS 내부 인터페이스 `br-provider`에 둡니다.

```text
실습 Windows PC(172.16.8.1) → Nginx 172.16.8.10:443
                              ├─ cloud.lab.test → FastAPI 127.0.0.1:8000
                              └─ grafana.lab.test → Grafana 127.0.0.1:3000
```

[웹 접속 설정](../automation/ansible/inventory/group_vars/control_nodes.yml)에 주소·방화벽 허용 범위를 모았습니다.
도메인은 실습 PC의 hosts로 해석하고 실습 CA를 신뢰 등록합니다. Nginx가 HTTPS를 처리하며 API·Grafana·Prometheus·Alertmanager는 루프백 주소에서 동작합니다.
VMnet8에 사용자 VM과 스토리지가 함께 있으므로 실제 운영 환경 수준의 망 분리를 구현한 것은 아닙니다.

## 공유 스토리지

`storage1(172.16.8.21)`과 `storage2(172.16.8.22)`의 `/srv/gluster/brick1/instances`를 GlusterFS `instance-volumes` 복제 볼륨으로 구성합니다.
control과 compute 두 대는 이를 `/var/lib/private-cloud/volumes`에 FUSE로 마운트합니다.

- `images/`: SHA-256을 확인한 클라우드 원본 이미지.
- VM 디스크: 원본 이미지를 참조하는 qcow2 변경분 디스크. 모든 VM마다 원본 전체를 복사하는 방식은 아닙니다.
- 두 데이터 디스크가 각각 10GB여도 복제 구성의 논리 용량은 합산 20GB가 아닙니다. 원본 이미지와 변경분이 같은 공간을 사용합니다.

GlusterFS는 VM 디스크를 저장하고, MariaDB는 사용자·VM·작업 메타데이터를 저장합니다. 서로의 복제 기능을 대신하지 않습니다.
원본 이미지를 사용하는 VM이 남아 있는 동안 해당 이미지를 임의로 변경·삭제해서는 안 됩니다.

## 보안과 자동 접근 관리

- 계정은 관리자가 생성합니다. 사용자는 자기 VM·키·지표만 조회하고, 관리자는 전체 운영 현황을 조회합니다.
- 비밀번호는 `pwdlib`의 Argon2 해시와 개별 무작위 솔트로 저장합니다. 사용자 개인키는 서버에 업로드하지 않습니다.
- 사용자 공개키와 control의 VM 관리용 공개키를 cloud-init으로 주입합니다. 기반 노드용 키와 사용자 VM 관리용 키는 분리합니다.
- `~/.ssh/config`가 `config.d/*.conf`를 읽습니다. 기반 노드 별칭은 Ansible이, 사용자 VM 별칭과 `[instances]` 인벤토리는 작업 처리기가 관리합니다.
- VM 생성·삭제 완료 및 작업 처리기 시작 시 DB 기준으로 접속 목록을 갱신합니다. 실행 중인 VM의 IP를 임의로 바꾼 경우까지 상시 추적하는 기능은 없습니다.
- 사용자 VM 호스트 키는 전용 `known_hosts`에서 첫 연결 시 신뢰하는 방식입니다. 운영 환경의 SSH 인증기관을 대체하지는 않습니다.
- SELinux는 유지하고 필요한 정책만 허용합니다. 세션 쿠키는 HTTPS에서 `Secure` 속성을 사용합니다.

## 관측과 한계

Prometheus는 기반 노드와 사용자 VM을 **10초** 주기로 수집합니다. 새 VM에는 node exporter를 기본 설치하고, VM 수집 대상 목록은 API에서 **30초**마다 갱신합니다.
일반 사용자는 소유자 검증을 거친 포털 API로 자기 지표만 받습니다. Grafana는 별도 로그인하는 운영자 도구이며 포털과 통합 로그인하지 않습니다.

수집 실패는 전원·네트워크·exporter 이상 중 하나를 나타내며, VM의 실제 전원 상태나 내부 애플리케이션 정상 여부를 단독으로 증명하지 않습니다.
현재는 같은 compute의 재기동 복구를 다루며 자동 장애 조치·라이브 마이그레이션·스토리지 arbiter는 구현 범위에 포함하지 않습니다.
