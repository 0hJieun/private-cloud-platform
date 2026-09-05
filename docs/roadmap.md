# 구축 진행 현황과 다음 단계

## 완료

- VMware outer lab과 management/provider 네트워크 분리
- control DHCP, compute KVM/libvirt·Open vSwitch, storage GlusterFS replica 2
- Rocky 9·Ubuntu 24.04 GenericCloud 이미지 카탈로그와 cloud-init 기반 inner VM 생성
- MariaDB, Alembic, FastAPI, Nginx portal, 단일 worker 기반 self-service control plane
- admin/member 역할, 사용자 SSH 공개키 등록, VM 비동기 생성·삭제와 soft delete 이력
- 자원 확인 기반 scheduler와 Ansible 프로비저너 연동
- Prometheus/node exporter infrastructure target, Grafana node·Gluster brick dashboard
- 선택형 managed instance node exporter와 owner-scoped portal monitoring 설계
- 모든 infrastructure 노드의 KST 시간 동기화(chrony)

## 현재 시연 범위

1. member가 공개키를 등록하고 Rocky 또는 Ubuntu 이미지를 선택해 VM 생성을 요청한다.
2. API는 `202 Accepted`와 작업 ID를 기록하고 worker가 scheduler로 compute를 고른다.
3. Ansible이 qcow2 overlay·cloud-init seed·libvirt domain을 만들고 control DHCP가 provider IP를 할당한다.
4. 사용자는 자신의 private key로 `clouduser@<provider-ip>`에 SSH 접속한다.
5. admin은 portal의 예약 자원과 Grafana의 host·storage 지표를 함께 확인한다. 관리형 모니터링을 선택한 member는 portal에서 자기 VM의 guest OS 지표만 확인한다.
6. 삭제 요청은 별도 operation으로 처리하고 `instances`에는 `DELETED` 이력을 남긴다.

## 의도적으로 다음 단계로 남긴 항목

- GlusterFS 3노드/arbiter, fencing, 자동 장애 조치
- 계획된 maintenance migration과 무중단 live migration
- 다중 worker를 위한 queue locking 전략과 고가용 control plane
- control-plane custom metrics, alert rule·notification
- CI, 취약점 검사, TLS와 외부 공개 ingress
- 보존 기간이 지난 삭제 instance의 archive/purge 배치 작업

## instance 상태 전이

```text
REQUESTED → SCHEDULING → PROVISIONING → WAITING_FOR_IP → ACTIVE
                                  └────────────────────→ ERROR
ACTIVE → DELETE_REQUESTED → DELETING → DELETED
```

API 요청 기록과 worker 실행을 분리하면 HTTP 요청이 끊겨도 작업 상태를 추적하고 재시도할 수 있다.
