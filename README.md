# 프라이빗 클라우드 플랫폼

KVM/libvirt, Open vSwitch, DHCP, storage, Ansible, cloud-init, Prometheus를 이용해 소형 프라이빗 클라우드 플랫폼을 구축하는 프로젝트입니다.

## 주요 기능

- 자원 상태를 기반으로 한 인스턴스 배치
- libvirt/KVM 기반 인스턴스 생명주기 관리
- Open vSwitch provider network와 DHCP 구성
- cloud-init 기반 초기화와 SSH public key 주입
- Ansible 기반 outer 인프라 구성과 inner VM runtime inventory 관리
- admin/member self-service portal과 SSH 공개키 등록
- Prometheus/Grafana 기반 관찰 가능성
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

## 저장소 구조

```text
infra/          # VMware outer lab과 이미지 빌드 정의
automation/     # Ansible과 cloud-init
control-plane/  # API, scheduler, worker, DB migration
admin-ui/       # 관리자 화면
monitoring/     # Prometheus, Grafana, 알림 규칙
scripts/        # 개발 및 검증용 보조 스크립트
tests/          # 단위, API, smoke test
docs/           # 공개 아키텍처 및 설치 문서
```

## 문서

- [아키텍처](docs/architecture.md)
- [첫 KVM 인스턴스 프로비저닝](docs/instance-provisioning.md)
- [최소 인스턴스 scheduler](docs/scheduling.md)
- [`cloudctl` 운영 CLI](docs/cloudctl.md)
- [구축 진행 현황과 다음 단계](docs/roadmap.md)
- [Control API와 MariaDB 상태 저장소](docs/control-api.md)
- [Control-plane 데이터 모델과 보존 정책](docs/data-model.md)
- [관찰 가능성 설계](docs/monitoring.md)
- [포털 UI와 관측 화면의 역할 분리](docs/portal-ui.md)
- [inner VM Ansible 자동 편입](docs/instance-automation.md)

## 현재 상태

VMware 기반 lab에서 control·compute 2대·storage 2대와 self-service portal, VM 생성/삭제,
Prometheus/Grafana 관찰 가능성까지 배포·검증했다. 남은 고가용성·migration·CI 범위는
[roadmap](docs/roadmap.md)에 의도적으로 분리해 둔다.

## 보안

인증 정보, private key, `.env` 파일, VM 이미지, VM 실행 데이터, 모니터링 데이터는 이 저장소에 커밋하지 않습니다.
