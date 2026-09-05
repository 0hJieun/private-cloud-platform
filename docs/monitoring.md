# 관찰 가능성 설계

이 플랫폼은 **infrastructure**, **control plane**, **managed instance**를 서로 다른
책임 경계로 관찰한다. 모든 Linux 시스템에 같은 agent를 무조건 넣는 것이 목적이
아니라, 누가 어떤 데이터에 접근할 수 있는지 먼저 정한다.

## 세 계층

| 계층 | 수집 대상 | 열람 주체 | 목적 |
|---|---|---|---|
| infrastructure | control, compute, storage의 node exporter | 운영자 Grafana | hypervisor 자원, Gluster brick, control 장애 판단 |
| control plane | API health, operation queue, instance lifecycle/예약 자원 | 운영자 portal·Grafana | 요청 처리 자체의 정상성 확인 |
| managed instance | 사용자가 선택한 guest의 node exporter | 소유자 portal, 운영자 portal | guest OS CPU·메모리·루트 디스크·네트워크 확인 |

Grafana는 infrastructure 운영자용이다. Grafana OSS의 Viewer는 같은 organization 안의
datasource를 질의할 수 있으므로, dashboard 변수로 VM 이름만 필터링해 일반 사용자에게
공유하는 것은 권한 격리가 아니다. 따라서 member 화면은 Grafana를 embed하거나 직접
노출하지 않고, 인증된 FastAPI가 소유자의 VM ID로 고정한 PromQL만 실행해 필요한 숫자를
반환한다.

## Managed instance 생성 흐름

```text
member가 portal에서 '관리형 모니터링'을 선택
  → instances.monitoring_enabled = true
  → worker가 cloud-init에 monitoring flag를 전달
  → guest가 node exporter를 checksum 검증 후 설치
  → guest firewall은 control provider IP(172.16.8.10)만 9100/tcp 허용
  → Prometheus HTTP service discovery가 API에서 ACTIVE target을 30초마다 조회
  → member는 portal에서 자기 instance_id 지표만 조회
```

Prometheus의 discovery endpoint는 session cookie가 아니라 `/etc/private-cloud/api.env`의
난수 Bearer token으로 보호한다. token이 포함된 `/etc/prometheus/prometheus.yml`은
`root:prometheus`, `0640`으로 배포한다. target label에는 `cloud_instance_id`와
`cloud_instance_name`만 넣고, 사용자명·SSH 키·비밀값은 넣지 않는다.

## 보안과 한계

- control의 `private-cloud-ansible` 키는 compute/storage 같은 infrastructure node 전용이다.
  새 tenant VM에는 VM 소유자가 등록한 공개키만 cloud-init으로 주입한다.
- VM 생성·삭제·IP 확인은 libvirt와 DHCP lease로 수행한다. 플랫폼이 tenant VM에 SSH로
  상시 접근할 필요가 없다.
- lab은 분리된 provider network와 source-IP firewall rule을 사용한다. production이라면
  exporter endpoint에 mTLS 또는 인증 프록시, 버전이 고정된 내부 artifact repository,
  agent patch 관리 정책을 추가해야 한다.
- 기존 VM에 `monitoring_enabled`를 소급 적용하지 않는다. owner가 명시적으로 새 managed
  VM을 요청하거나, 별도 migration 작업을 승인해야 한다.

## Grafana dashboard-as-code와 portal의 차이

Grafana JSON dashboard는 운영자에게 여러 노드·모든 target의 관계와 시계열을 탐색하게
한다. portal의 managed monitoring 카드는 사용자에게 필요한 현재 상태만 제한해 보인다.
둘은 중복이 아니라 **운영자 observability**와 **사용자 self-service**라는 다른 제품
경계다.
