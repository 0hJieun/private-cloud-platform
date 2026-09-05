# 구축 진행 현황과 다음 단계

## 완료

- VMware outer lab과 관리/provider 네트워크 분리
- control DHCP, compute KVM/libvirt·Open vSwitch, storage GlusterFS replica 2
- GenericCloud 이미지 라이브러리와 cloud-init 기반 inner VM 생성
- 자원 확인 기반 scheduler와 `cloudctl` lifecycle 검증

## 진행 중: control API와 상태 저장소

- MariaDB에 인스턴스 요청·상태·배치 결과를 저장
- FastAPI가 `/health`, `/v1/images`, `/v1/instances` HTTP 계약 제공
- 생성 요청은 먼저 `REQUESTED`로 저장

## 다음

1. worker가 `REQUESTED`를 scheduler·Ansible 작업으로 실행하고 상태를 전이
2. DHCP lease를 수집해 `provider_ip`와 SSH 준비 상태 반영
3. Nginx reverse proxy와 관리자 웹 화면 추가
4. Ubuntu GenericCloud를 이미지 카탈로그에 추가
5. Prometheus/Grafana, 실패 복구·migration·CI 시나리오 구현

## instance 상태 전이

```text
REQUESTED → SCHEDULING → PROVISIONING → WAITING_FOR_IP → ACTIVE
                                  └────────────────────→ ERROR
ACTIVE → DELETING → DELETED
```

API 요청 기록과 worker 실행을 분리하면 HTTP 요청이 끊겨도 작업 상태를 추적하고 재시도할 수 있다.
