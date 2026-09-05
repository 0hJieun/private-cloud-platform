# 프라이빗 클라우드 플랫폼

KVM/libvirt, Open vSwitch, DHCP, storage, Ansible, cloud-init, Prometheus를 이용해 소형 프라이빗 클라우드 플랫폼을 구축하는 프로젝트입니다.

## 주요 기능

- 자원 상태를 기반으로 한 인스턴스 배치
- libvirt/KVM 기반 인스턴스 생명주기 관리
- Open vSwitch provider network와 DHCP 구성
- cloud-init 기반 초기화와 SSH public key 주입
- Ansible 기반 outer 인프라 구성과 inner VM runtime inventory 관리
- admin/member self-service portal과 SSH 공개키 등록
- Prometheus/Grafana/Alertmanager 기반 관찰 가능성 및 Slack 알림 연동
- 선택형 managed instance monitoring과 owner-scoped portal 지표
- GlusterFS replica 기반 이미지·볼륨 관리

## 아키텍처

```text
control ── API / scheduler / MariaDB / DHCP / monitoring
   ├── compute1 ── libvirt/KVM / Open vSwitch
   ├── compute2 ── libvirt/KVM / Open vSwitch
   ├── storage1 ── GlusterFS replica data
   └── storage2 ── GlusterFS replica data
```

portal은 control의 Nginx(`172.16.2.10:8080`)가 FastAPI(`127.0.0.1:8000`)를 reverse proxy하는 구조다. 이 lab은 관리망 HTTP로만 제공하며, 외부 공개 환경에서는 TLS termination·HTTPS-only cookie·별도 ingress 정책을 추가한다.

## 실제 저장소 구조

```text
infra/packer/                 # Rocky 9 base image Packer 정의
infra/vmware/                 # VMware lab.yml, outer VM 생성·사양 조정 PowerShell
automation/ansible/           # inventory, Ansible playbook, runtime instance inventory adapter
control-plane/api/            # FastAPI, SQLAlchemy model, Alembic migration, portal static UI
control-plane/worker/         # DB operation을 claim해 Ansible/libvirt 작업을 실행하는 worker
control-plane/scheduler/      # compute 배치 후보 선택 로직과 cloudctl
monitoring/                   # Prometheus, Alertmanager, Grafana provisioning artifact
tests/unit/                   # scheduler, migration, portal API 단위 테스트
docs/                         # 설계·운영·시연 문서
```

초기 scaffolding에서 남았던 빈 `admin-ui/`, `scripts/`, 별도 `control-plane/app/`·`migrations/`·`tests/`는
제거했다. portal UI의 실제 위치는 `control-plane/api/app/static/`이며, `packer_cache/`는 Git이 무시하는
Packer의 로컬 build cache이므로 소스 구조에는 포함하지 않는다.

## 문서

- [아키텍처](docs/architecture.md)
- [첫 KVM 인스턴스 프로비저닝](docs/instance-provisioning.md)
- [최소 인스턴스 scheduler](docs/scheduling.md)
- [`cloudctl` 운영 CLI](docs/cloudctl.md)
- [구축 진행 현황과 다음 단계](docs/roadmap.md)
- [Control API와 MariaDB 상태 저장소](docs/control-api.md)
- [Control-plane 데이터 모델과 보존 정책](docs/data-model.md)
- [GlusterFS 스토리지 설계와 운영 범위](docs/storage.md)
- [관찰 가능성 설계](docs/monitoring.md)
- [포털 UI와 관측 화면의 역할 분리](docs/portal-ui.md)
- [inner VM Ansible 자동 편입](docs/instance-automation.md)
- [최종 장애·DB 시연 Runbook](docs/final-demo-runbook.md)

## 현재 상태

VMware 기반 lab에서 control·compute 2대·storage 2대, self-service portal, VM 생성/삭제,
runtime Ansible inventory, Prometheus/Grafana/Alertmanager 구성을 코드화했다. 실제 Slack 통지는
control의 root 전용 secret에 Incoming Webhook을 넣은 뒤 monitoring playbook을 적용해 활성화한다.
남은 storage HA·migration·CI 범위는 [roadmap](docs/roadmap.md)에 의도적으로 분리해 둔다.

## 보안

인증 정보, private key, `.env` 파일, VM 이미지, VM 실행 데이터, 모니터링 데이터는 이 저장소에 커밋하지 않습니다.
