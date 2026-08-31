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
- `storage`: NFS 이미지 저장소, 백업 대상
- `storage1`, `storage2`: GlusterFS 데이터 노드
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

## Instance 생명주기

```text
REQUESTED → SCHEDULING → IMAGE_PREPARING → CREATING
→ WAITING_FOR_IP → CONFIGURING → ACTIVE
```

오류가 발생하면 `ERROR` 상태로 전환하고, 중간에 생성된 볼륨·lease·DB reservation을 정리합니다.
