# 프라이빗 클라우드 플랫폼

KVM/libvirt, Open vSwitch, DHCP, storage, Ansible, cloud-init, Prometheus를 이용해 소형 프라이빗 클라우드 플랫폼을 구축하는 프로젝트입니다.

## 주요 기능

- 자원 상태를 기반으로 한 인스턴스 배치
- libvirt/KVM 기반 인스턴스 생명주기 관리
- Open vSwitch provider network와 DHCP 구성
- cloud-init 기반 초기화와 SSH public key 주입
- Ansible 기반 인프라 구성 및 동적 inventory 관리
- Prometheus/Grafana 기반 관찰 가능성
- NFS와 GlusterFS를 이용한 이미지·볼륨 관리

## 아키텍처

```text
control ── API / scheduler / MariaDB / DHCP / monitoring
   ├── compute1 ── libvirt/KVM / Open vSwitch
   ├── compute2 ── libvirt/KVM / Open vSwitch
   ├── storage1 ── GlusterFS replica data
   └── storage2 ── GlusterFS replica data
```

관리자 페이지는 control 내부의 Nginx, WAS, MariaDB로 구성합니다.

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

## 현재 상태

개발 진행 중입니다. 재현 가능한 설정과 검증 절차를 단계적으로 구축하고 있습니다.

## 보안

인증 정보, private key, `.env` 파일, VM 이미지, VM 실행 데이터, 모니터링 데이터는 이 저장소에 커밋하지 않습니다.
