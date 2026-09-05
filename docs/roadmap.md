# 구축 진행 현황과 다음 단계

## 완료

- VMware outer lab과 관리/provider 네트워크 분리
- control DHCP, compute KVM/libvirt·Open vSwitch, storage GlusterFS replica 2
- GenericCloud 이미지 라이브러리와 cloud-init 기반 inner VM 생성
- 자원 확인 기반 scheduler와 `cloudctl` lifecycle 검증

## 진행 중: self-service control plane

- MariaDB에 사용자·SSH key·이미지·compute·인스턴스·작업·이벤트를 저장
- FastAPI가 session 인증과 role 기반 API를 제공
- worker가 `REQUESTED`와 `DELETE` 작업을 scheduler·Ansible로 실행

## 다음

1. 로그인·SSH key 등록·VM 생성/삭제 웹 화면 추가
2. Ubuntu GenericCloud를 이미지 카탈로그에 추가
3. Prometheus/Grafana와 admin resource dashboard 추가
4. 실패 복구·migration·CI 시나리오 보강

## instance 상태 전이

```text
REQUESTED → SCHEDULING → PROVISIONING → WAITING_FOR_IP → ACTIVE
                                  └────────────────────→ ERROR
ACTIVE → DELETE_REQUESTED → DELETING → DELETED
```

API 요청 기록과 worker 실행을 분리하면 HTTP 요청이 끊겨도 작업 상태를 추적하고 재시도할 수 있다.
