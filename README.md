# Private Cloud Platform

VMware Workstation 위에 구축한 소형 IaaS control plane입니다. 사용자는 portal에서 SSH 공개키·이미지·flavor를 선택해 VM을 요청하고, control plane은 MariaDB 작업 큐, scheduler, Ansible, libvirt/KVM으로 비동기 생성·삭제를 처리합니다.

## Highlights

- FastAPI/Nginx portal과 admin/member 역할 기반 self-service
- MariaDB + Alembic 기반 요청, 작업, 상태 전이 audit trail
- 예약 vCPU·메모리와 실제 host 상태를 함께 보는 compute scheduler
- libvirt/KVM, Open vSwitch, control DHCP, cloud-init SSH key injection
- GlusterFS replica 2 기반 shared image/instance volume
- Prometheus, Grafana, Alertmanager 및 Slack 장애 알림
- 새 inner VM의 Ansible runtime inventory와 SSH alias 자동 관리

## Architecture

```text
Browser → Nginx portal → FastAPI → MariaDB (desired state / operation / event)
                                  └→ worker → scheduler → Ansible → libvirt/KVM

control ── DHCP / monitoring / control plane
  ├── compute1, compute2 ── KVM/libvirt + OVS
  └── storage1, storage2 ── GlusterFS replica 2
```

Provider network는 `172.16.8.0/24`, management network는 `172.16.2.0/24`로 분리한다. FastAPI와 Prometheus/Alertmanager는 control의 loopback에만 열고, Nginx와 Grafana만 management network에서 제공한다.

## Repository layout

```text
infra/             # Packer image definition, VMware outer-lab automation
automation/        # Ansible inventory and infrastructure playbooks
control-plane/     # API, Alembic schema, worker, scheduler, portal static assets
monitoring/        # Prometheus rules, Alertmanager, Grafana dashboard provisioning
tests/             # unit tests
docs/              # architecture, data model, operations
```

## Design documents

- [Architecture](docs/architecture.md)
- [MariaDB data model](docs/data-model.md)
- [Operations, monitoring, and storage](docs/operations.md)

## Scope and limits

The lab demonstrates instance lifecycle automation, shared replicated storage, observability, and planned failure detection/recovery. It does not claim production-grade HA: GlusterFS replica 2 has no arbiter/fencing, MariaDB is single-node, and compute failure does not trigger automatic migration to another compute node.

## Security

Private keys, passwords, environment files, VM images, runtime data, and monitoring data are excluded from Git. Slack Webhook URLs are stored only in a root-readable secret file on control.
