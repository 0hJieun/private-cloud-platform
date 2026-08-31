# Cloud Platform Lab

KVM/libvirt, Open vSwitch, DHCP, storage, Ansible, cloud-init, monitoring을 이용해 소형 프라이빗 클라우드 플랫폼을 구축하는 학습 프로젝트입니다.

## 목표

- compute 자원을 비교해 인스턴스를 자동 배치한다.
- cloud-init으로 인스턴스를 초기화한다.
- Ansible로 인프라와 인스턴스를 관리한다.
- Prometheus와 Grafana로 상태를 관찰한다.
- NFS와 GlusterFS의 역할과 장애 상황을 비교한다.

## 구조

```text
control ── scheduler/API/DB/DHCP/monitoring
   ├── compute1 ── libvirt/KVM/OVS
   ├── compute2 ── libvirt/KVM/OVS
   ├── storage  ── NFS/image repository
   ├── storage1 ── GlusterFS data
   └── storage2 ── GlusterFS data
```

## 진행 상태

- [ ] VMware 네트워크와 기본 VM 구성
- [ ] Ansible 공통 설정
- [ ] control DHCP
- [ ] compute libvirt와 OVS
- [ ] 단일 인스턴스 생성
- [ ] compute 스케줄러
- [ ] cloud-init과 SSH key
- [ ] 동적 Ansible inventory
- [ ] NFS
- [ ] GlusterFS
- [ ] Prometheus/Grafana
- [ ] 관리자 페이지
- [ ] 장애 테스트와 운영 문서

## 문서

- [아키텍처](docs/architecture.md)
- [학습 및 구현 순서](docs/roadmap.md)
- [운영 기록](docs/operations.md)
- [의사결정 기록](docs/adr/README.md)

## 보안 및 저장소 원칙

비밀번호, private key, `.env`, qcow2 이미지, VM 데이터, Prometheus 데이터는 저장소에 커밋하지 않습니다.

## 상태

현재는 초기 설계 단계입니다.
