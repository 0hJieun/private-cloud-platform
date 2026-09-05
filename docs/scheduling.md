# 최소 인스턴스 scheduler

현재 scheduler는 control-plane worker가 호출하는 Python 배치 결정 모듈이다. API가 MariaDB에 요청·예약 상태를 기록한 뒤 worker가 실행 시점의 각 compute libvirt domain과 host memory를 다시 읽어 배치 후보를 계산한다.

## 왜 Ansible과 분리하는가

Ansible의 역할은 선택된 노드에 원하는 상태를 적용하는 **프로비저너**다. 반면 scheduler의 역할은 여러 compute 중 하나를 고르고, 부족한 자원을 거절하며, 어떤 노드를 골랐는지 보여 주는 **의사결정**이다.

```text
사용자 요청
  → scheduler.py: compute의 현재 domain/메모리 확인 및 대상 선택
  → provision-instance.yml: 선택된 compute에 qcow2·cloud-init·libvirt 적용
  → DHCP: inner VM에 provider IP 할당
```

API와 MariaDB는 요청 상태와 reservation을, worker는 작업 claim과 상태 전이를, scheduler는 compute 선택만 담당한다. 이 분리는 UI/API·작업 재시도·배치 정책을 서로 독립적으로 바꾸기 위한 것이다.

## 판단 기준

각 compute outer VM은 3 vCPU와 6GB RAM이지만, host OS와 libvirt에 자원을 남긴다. inventory에는 다음의 보수적 한도를 정의한다.

| 항목 | 노드당 배치 한도 |
|---|---:|
| vCPU | 2 |
| 메모리 | 4096MB |

scheduler는 정의된 모든 libvirt domain(켜진 VM과 꺼진 VM 모두)의 vCPU·메모리를 예약량으로 합산한다. 요청을 수용할 수 있는 노드 중 VM 수가 가장 적은 후보를 먼저 고르고, VM 수가 같으면 `/proc/stat`을 0.5초 간격으로 두 번 읽어 계산한 현재 CPU 사용률, 예약 메모리, 예약 vCPU 순으로 비교한다. 또한 `/proc/meminfo`의 실제 가용 메모리가 요청량보다 512MB 이상 여유 있는지 검사한다.

CPU 사용률은 짧은 시간의 순간값이라 **수용 가능 여부를 거절하는 hard limit**으로 쓰지 않는다. hard limit은 inventory의 예약 vCPU·메모리와 실제 가용 메모리로 판단하고, CPU 사용률은 둘 다 수용 가능한 후보 사이의 tie-breaker로만 쓴다. 이 방식은 일시적인 CPU spike 때문에 정상 요청을 불필요하게 거절하지 않는다.

이 방식은 단일 control 운영자 기준이다. 동시에 여러 요청이 들어올 때의 경쟁 조건은 DB reservation과 작업 큐를 추가하는 control-plane 단계에서 해결한다.

## 현재 호출 경로

정상 경로는 portal의 생성 요청이다.

```bash
browser portal
  → POST /v1/instances
  → MariaDB operation(PENDING)
  → private-cloud-worker
  → scheduler.py
  → provision-instance.yml
```

`scheduler.py` 또는 `cloudctl`의 direct 실행은 초기 실습·단위 테스트를 위한 진단 경로로 남아 있다. 현재 portal lifecycle을 우회하므로 일상 VM 생성에는 사용하지 않는다.
