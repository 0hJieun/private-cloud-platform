# Private Cloud Platform

사내 개발·테스트용 서버 제공을 가정한 **VM 생성·운영 자동화 플랫폼**입니다.
사용자는 웹에서 운영체제·사양·SSH 공개키를 선택하고, 플랫폼은 배치 노드 선정부터 VM 생성·접속 정보 등록·모니터링·삭제까지 처리합니다.
VMware Workstation 안에 KVM 가상화 환경을 구성한 개인 인프라 프로젝트입니다.

## 주요 기능

| 기능 | 구현 내용 |
|---|---|
| 사용자·관리자 포털 | 사용자는 자신의 VM과 지표를 조회하고, 관리자는 전체 VM·소유자·노드별 예약 자원을 확인 |
| 비동기 생성·삭제 | FastAPI가 요청을 MariaDB에 기록하고 작업 처리기(worker)가 Ansible·libvirt를 실행 |
| 자원 기반 배치 | 예약 자원과 실제 가용 메모리로 후보를 거른 뒤 VM 수·CPU 사용률 등을 비교. 이름 중복·용량 부족 사전 검사 |
| 네트워크·공유 디스크 | OVS 가상 스위치, control DHCP, VMware NAT와 GlusterFS 2중 복제 볼륨 사용 |
| 접근 관리 | 사용자 공개키 주입, 별도 관리용 키, VM 생성·삭제에 따른 Ansible 인벤토리·SSH 별칭 갱신 |
| 모니터링·알림 | 기반 노드와 내부 VM 지표 수집, Grafana 대시보드, Slack 장애·복구 알림 |

## 전체 구조

```text
브라우저 → Nginx(HTTPS) → FastAPI → MariaDB(사용자·VM·작업·이력)
                                     ↑↓
                                  작업 처리기
                                     ↓
                           스케줄러 → Ansible
                                     ↓
                         compute1·2의 libvirt/KVM
                            ├─ OVS → DHCP / NAT
                            └─ GlusterFS 공유 VM 디스크

노드·VM의 node exporter → Prometheus ┬─ Grafana / 소유자별 포털 지표
                                    └─ Alertmanager → Slack
```

| 노드 | 수량 | VMware에 할당한 사양 | 역할 |
|---|---:|---|---|
| control | 1 | 2 vCPU / 4GB RAM / OS 디스크 20GB | API·DB·작업 처리·DHCP·Ansible·모니터링 |
| compute | 2 | 각 3 vCPU / 6GB RAM / OS 디스크 20GB | KVM 인스턴스 실행, OVS 네트워크 |
| storage | 2 | 각 1 vCPU / 2GB RAM / OS 20GB + 데이터 10GB | GlusterFS 복제 볼륨 |

compute의 **VM 배치 한도는 각 2 vCPU / 4GB**로, 호스트에 할당한 사양과 다릅니다.
호스트 운영 여유분을 남기는 정책이며 [노드 사양](infra/vmware/lab.yml)과 [배치 한도](automation/ansible/inventory/hosts.yml)를 분리해 관리합니다.

## 확인한 운영 흐름

- 공개키 선택 → Ubuntu VM 생성 → compute 자동 배치 → 사용자 SSH 접속.
- control에서 자동 생성된 SSH 별칭으로 접속하고, 새 VM이 모니터링 대상에 추가되는 과정.
- compute 전원 차단 → 노드·VM 수집 실패 → Slack·Grafana·포털 반영 → 같은 compute 재기동 후 복구 확인.
- VM 이름 재입력 후 삭제 → 예약 자원 반환 → 모니터링 대상·실제 libvirt 목록 정리.

장애 시연은 격리된 실습 환경에서 수행했습니다. 다른 compute로의 자동 이동이나 무중단 복구를 의미하지 않습니다.

## 저장소 안내

```text
infra/          # Packer 기반 이미지와 VMware 노드 생성 스크립트
automation/     # Ansible 인벤토리, 기반 노드 구성과 VM 생성·삭제
control-plane/  # FastAPI·웹 화면·DB 스키마·작업 처리기·스케줄러
monitoring/     # Prometheus·Alertmanager 설정과 Grafana 대시보드
tests/          # 단위 테스트와 알림 규칙 테스트
docs/           # 아키텍처·데이터 모델·운영 방법
```

- [아키텍처](docs/architecture.md): 네트워크, 요청 처리, 스케줄링과 보안 경계.
- [데이터 모델](docs/data-model.md): 8개 테이블, 관계, 삭제 이력과 무결성 규칙.
- [설치·운영](docs/operations.md): 구성 순서, HTTPS 접속, 배포·점검 명령.

포털은 `https://cloud.lab.test`, 운영자 Grafana는 `https://grafana.lab.test`입니다.
실습 PC의 이름 해석·인증서 신뢰 설정이 필요하며, 현재는 VMware 호스트 PC만 접근하도록 제한했습니다. 공개 서비스 주소가 아닙니다.

## 테스트

저장소 루트의 Python 가상환경에서 실행합니다. VM이나 운영 DB를 변경하지 않는 테스트입니다.

```bash
python -m pip install -r control-plane/api/requirements.txt Jinja2 PyYAML
python -m unittest discover -s tests/unit -v
```

Prometheus 규칙은 `promtool test rules tests/monitoring/alert-timing.test.yml`로 별도 검증합니다.

## 범위와 한계

- GlusterFS는 데이터 노드 2대의 복제 구성입니다. arbiter·펜싱을 포함한 완전한 고가용성 구성은 아닙니다.
- control과 MariaDB는 단일 노드이며, compute 장애 시 다른 노드로 VM을 자동 이동하지 않습니다.
- 모든 기반 VM이 한 대의 물리 PC에 있으므로 물리 장애 영역이 분리되어 있지 않습니다.
- 실제 운영 환경으로 확장하려면 사용자·스토리지망 분리, 비밀값 관리 강화, 백업·복구와 작업 처리기 장애 복구가 추가로 필요합니다.

개인키·비밀번호·환경 파일·VM 이미지·실행 데이터는 Git에 저장하지 않습니다.
