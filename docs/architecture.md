# 아키텍처

## 범위

이 프로젝트는 VMware Workstation 실습 환경에서 동작하는 소형 IaaS 형태의 control plane입니다. VMware는 outer lab 환경을 제공하고, 구축 대상 플랫폼은 control, compute, storage, instance 계층으로 구성됩니다.

## 네트워크

| 네트워크 | 용도 | 예시 대역 |
|---|---|---|
| vmnet2 | 관리 네트워크 | `172.16.2.0/24` |
| vmnet8 | provider/instance 네트워크 | `172.16.8.0/24` |

control node가 관리하는 네트워크에서는 VMware DHCP 서비스를 비활성화합니다.

## 구성 요소

- `control`: API, scheduler, MariaDB, DHCP, Ansible, Prometheus, Grafana, 관리자 웹 애플리케이션
- `compute1`, `compute2`: libvirt/KVM, Open vSwitch
- `storage1`, `storage2`: GlusterFS replica 2 데이터 노드
- instance: cloud-init으로 초기화하고 Ansible로 관리하는 libvirt guest

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
      └── 동적 Ansible inventory 생성
```

cloud-init은 instance가 부팅된 뒤 최초 설정을 수행합니다. VMware Workstation VM을 생성하는 주 도구는 아닙니다. Outer VM 이미지는 Packer로 만들고, guest 설정은 Ansible로 관리합니다. 호스트 수준의 VMware 네트워크 설정은 실행 환경에 따라 달라질 수 있습니다.

GlusterFS 볼륨은 두 storage 노드에 replica 2로 구성한다. 이는 한 brick 장애 뒤에도 데이터 사본을 유지하기 위한 구성이다. 다만 2노드 구성만으로 split-brain 방지와 fencing을 포함한 완전한 HA가 되지는 않으므로, 자동 장애 조치와 유지보수 migration은 별도 운영 시나리오로 구현한다.

## 스토리지 토폴로지

`storage1(172.16.8.21)`과 `storage2(172.16.8.22)`는 provider 네트워크에서 GlusterFS trusted storage pool을 구성한다. `instance-volumes`는 두 노드의 `/srv/gluster/brick1/instances` brick을 사용하는 replica 2 볼륨이다. compute 노드는 이후 이 볼륨을 FUSE 클라이언트로 마운트해 인스턴스 qcow2 볼륨을 공유한다.

## Instance 생명주기

```text
REQUESTED → SCHEDULING → IMAGE_PREPARING → CREATING
→ WAITING_FOR_IP → CONFIGURING → ACTIVE
```

오류가 발생하면 `ERROR` 상태로 전환하고, 중간에 생성된 볼륨·lease·DB reservation을 정리합니다.
