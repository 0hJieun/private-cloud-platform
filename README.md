# Cloud Platform Lab

KVM/libvirt, Open vSwitch, DHCP, storage, Ansible, cloud-init, Prometheus를 이용해 소형 프라이빗 클라우드 플랫폼을 구축하는 프로젝트입니다.

## What it demonstrates

- 자원 상태를 기반으로 한 인스턴스 배치
- libvirt/KVM 기반 인스턴스 생명주기 관리
- Open vSwitch provider network와 DHCP
- cloud-init 기반 초기화와 SSH key 주입
- Ansible 기반 인프라 구성 및 동적 inventory
- Prometheus/Grafana 기반 관찰 가능성
- NFS와 GlusterFS를 이용한 이미지·볼륨 관리

## Architecture

```text
control ── API / scheduler / MariaDB / DHCP / monitoring
   ├── compute1 ── libvirt/KVM / Open vSwitch
   ├── compute2 ── libvirt/KVM / Open vSwitch
   ├── storage  ── NFS image repository
   ├── storage1 ── GlusterFS data
   └── storage2 ── GlusterFS data
```

관리자 페이지는 control 내부의 Nginx, WAS, MariaDB로 구성합니다.

## Repository layout

```text
infra/          # VMware outer lab and image build definitions
automation/     # Ansible and cloud-init
control-plane/  # API, scheduler, worker, database migrations
admin-ui/       # administrator interface
monitoring/     # Prometheus, Grafana, alert rules
scripts/        # small development and verification helpers
tests/          # unit, API, and smoke tests
docs/           # public architecture and setup documentation
```

## Documentation

- [Architecture](docs/architecture.md)

## Status

Work in progress. The repository is being built incrementally with reproducible configuration and verification steps.

## Security

Credentials, private keys, `.env` files, VM images, VM runtime data, and monitoring data are not committed to this repository.
