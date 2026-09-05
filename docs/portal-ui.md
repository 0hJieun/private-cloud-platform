# Portal UI와 관측 화면의 역할 분리

## 목적

이 프로젝트의 포털은 VM을 만들고 운영 상태를 확인하는 **control plane**이다.
Grafana를 그대로 포털에 내장하거나 모든 사용자에게 Prometheus를 열어 주지 않는다.
그렇게 하면 일반 사용자가 다른 VM·인프라 지표를 임의 조회할 수 있어 멀티테넌트
경계가 흐려지고, 운영 화면의 책임도 불명확해진다.

## 사용자 화면

member는 다음 화면만 사용한다.

- **개요**: 내 인스턴스 수, 실행 중 VM, 관리형 모니터링 선택 수, 최근 요청
- **인스턴스**: 본인이 소유한 VM의 상태, 배치, 접속 정보, 상세과 작업 이력
- **VM 생성**: 이미지·flavor·공개키·관리형 모니터링을 선택해 durable operation 생성
- **SSH 키**: 개인키가 아닌 공개키 등록

VM 생성 form은 입력 중 `POST /v1/instances/preflight`으로 다음을 확인한다.

- 전 사용자 기준으로 같은 `active_name`이 이미 있는지
- DB reservation 기준으로 요청 vCPU·메모리를 수용할 compute가 한 대 이상 있는지

중복 이름 또는 예약 수용 불가이면 생성 버튼을 비활성화한다. 다만 이 결과는 빠른
UX를 위한 사전 검사다. 동시 요청과 실제 host의 순간 메모리 변화가 있을 수 있으므로,
worker scheduler가 libvirt domain과 live memory를 다시 확인하는 것이 최종 판단이다.

인스턴스 상세의 monitoring 카드는 API가 인스턴스 소유권을 확인한 뒤, 고정된
PromQL로 조회한 현재 CPU·메모리·디스크·네트워크 값만 반환한다. 브라우저가 임의
PromQL을 실행하거나 타인의 VM을 조회할 수 없다.

## 관리자 화면

admin은 member와 같은 인스턴스 화면에서 전체 VM을 조회할 수 있다. 각 행에는
`owner_username`, 이미지, 요청 자원, 상태, 배치 compute, provider IP가 보인다.

별도의 **운영 센터**에서는 다음을 보인다.

- 사용자 수, 실행·처리 VM 수, 대기 operation 수
- compute별 scheduler 예약 vCPU/메모리
- compute에 실제로 배치된 VM 목록: VM 이름, 소유자, 요청 자원, lifecycle 상태
- 상세 시간 그래프용 Grafana 링크

`owner_username`은 `InstanceRead` API 표현에 포함한다. member의 `/v1/instances`
조회는 기존처럼 owner filter를 먼저 적용하므로, 이 필드는 자신의 사용자명만
노출한다. admin만 전체 소유자 매핑을 본다.

## Grafana

Grafana는 admin 운영 분석 전용이며 두 dashboard를 provision한다.

1. `Private Cloud Node Overview`: control, compute, storage, GlusterFS의 외부 노드 상태
2. `Private Cloud Instance Operations`: `cloud_instance_name` 변수로 관리형 VM을
   선택하고 CPU, 메모리, 루트 디스크, 네트워크, exporter 수집 상태를 시간축으로 분석

두 dashboard JSON은 Git에서 관리하고 Ansible이 `/etc/grafana/provisioning/dashboards`에
배포한다. Grafana UI에서 탐색할 수는 있지만, 재현 가능한 기본 운영 화면의 source of
truth는 repository의 JSON이다.
