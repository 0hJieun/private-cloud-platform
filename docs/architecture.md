# 아키텍처

## 범위

이 프로젝트는 VMware Workstation 실습 환경에서 동작하는 소형 IaaS 형태의 control plane입니다. VMware는 outer lab 환경을 제공하고, 구축 대상 플랫폼은 control, compute, storage, instance 계층으로 구성됩니다.

## 네트워크

| 네트워크 | 용도 | 예시 대역 |
|---|---|---|
| vmnet2 | 관리 네트워크 | `172.16.2.0/24` |
| vmnet8 | provider/instance 네트워크 | `172.16.8.0/24` |

control node가 관리하는 네트워크에서는 VMware DHCP 서비스를 비활성화합니다.

control의 `dhcpd`는 provider NIC(`ens192`)에서만 동작하며 `172.16.8.151–172.16.8.239`를 instance DHCP 풀로 사용한다. control·compute·storage의 고정 provider 주소는 이 범위 밖에 두고, instance 기본 게이트웨이는 VMware NAT 게이트웨이 `172.16.8.2`로 설정한다.

## 구성 요소

- `control`: Nginx portal, FastAPI, MariaDB, worker, scheduler, DHCP, Ansible, Prometheus, Alertmanager, Grafana
- `compute1`, `compute2`: libvirt/KVM, Open vSwitch
- `storage1`, `storage2`: GlusterFS replica 2 데이터 노드
- instance: cloud-init으로 초기화하고 사용자 SSH 공개키로 접속하며, 새 VM은 control 전용 automation 키로 Ansible 관리 대상에 자동 편입되는 libvirt guest

## Control-plane 요청 경로

```text
browser
  └── http://172.16.2.10:8080 (Nginx)
        └── FastAPI :8000 (localhost only)
              ├── MariaDB: users / instances / operations / events
              └── worker: scheduler → Ansible → libvirt/KVM
```

`POST /v1/instances`는 실제 VM 생성을 기다리지 않고 `202 Accepted`와 함께 MariaDB에
`CREATE/PENDING` operation을 남긴다. 독립 worker가 작업을 가져가 현재 libvirt 예약량을
비교하고 compute를 선택한 뒤, 선택된 노드에서 Ansible 프로비저너를 실행한다.

## 프로비저닝 계층

```text
VMware Workstation
  └── outer lab VM
      ├── Packer 이미지 정의
      └── Ansible 호스트 구성

control plane
  └── libvirt instance
      ├── qcow2 볼륨 준비
      ├── cloud-init seed 생성
      ├── DHCP lease 확인
      └── DHCP IP 확인 후 runtime Ansible inventory 갱신
```

cloud-init은 instance가 부팅된 뒤 최초 설정을 수행합니다. VMware Workstation VM을 생성하는 주 도구는 아닙니다. Outer VM 이미지는 Packer로 만들고, guest 설정은 Ansible로 관리합니다. 호스트 수준의 VMware 네트워크 설정은 실행 환경에 따라 달라질 수 있습니다.

GlusterFS 볼륨은 두 storage 노드에 replica 2로 구성한다. 이는 한 brick 장애 뒤에도 데이터 사본을 유지하기 위한 구성이다. 다만 2노드 구성만으로 split-brain 방지와 fencing을 포함한 완전한 HA가 되지는 않으므로, 자동 장애 조치와 유지보수 migration은 별도 운영 시나리오로 구현한다.

## 스토리지 토폴로지

`storage1(172.16.8.21)`과 `storage2(172.16.8.22)`는 provider 네트워크에서 GlusterFS trusted storage pool을 구성한다. `instance-volumes`는 두 노드의 `/srv/gluster/brick1/instances` brick을 사용하는 replica 2 볼륨이다. compute 노드는 이후 이 볼륨을 FUSE 클라이언트로 마운트해 인스턴스 qcow2 볼륨을 공유한다.

control과 compute는 `172.16.8.21`을 기본 volfile 서버로, `172.16.8.22`를 backup volfile 서버로 사용해 `/var/lib/private-cloud/volumes`에 볼륨을 마운트한다. control은 이 경로의 `images/`에 검증된 GenericCloud 베이스 이미지를 보관하고, compute는 인스턴스 디스크를 생성·실행한다. 따라서 인스턴스 디스크는 어느 compute에서 생성하더라도 두 compute가 같은 파일을 볼 수 있다.

## Instance 생명주기

```text
REQUESTED → SCHEDULING → PROVISIONING → WAITING_FOR_IP → ACTIVE
ACTIVE → DELETE_REQUESTED → DELETING → DELETED
```

생성·삭제 도중 오류가 발생하면 해당 instance는 `ERROR`, operation은 `FAILED`가 되고 오류 원인은
MariaDB의 operation·event 이력에 남는다. `DELETED` instance 행은 soft delete로 보존하며,
운영 목록과 scheduler는 `deleted_at IS NULL` 행만 사용한다.

## 관찰 가능성

각 control·compute·storage 노드는 node exporter로 `:9100/metrics`를 노출한다. Prometheus는
control에서 15초마다 5개 target을 수집하고 7일간 TSDB에 보관한다. Grafana는 management IP의
`:3000`에서만 제공하며, Git으로 관리하는 dashboard JSON을 Ansible이 provisioning 경로에 배포한다.

새 instance는 cloud-init으로 node exporter를 설치하고 control Prometheus만 9100/tcp로 접근할 수
있게 한다. 일반 member는 Grafana datasource를 직접 사용하지
않고, portal API가 owner 권한을 확인해 해당 VM의 지표만 반환한다. Alertmanager, GlusterFS 운영 범위와
장애 판단 경계는 [운영과 관찰 가능성](operations.md)에 기록한다.
