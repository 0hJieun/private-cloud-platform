# 최소 인스턴스 scheduler

이 단계의 scheduler는 control에서 실행하는 Python 운영 도구다. API와 MariaDB가 아직 없으므로 데이터베이스에 상태를 저장하지 않고, 실행 시점에 각 compute의 libvirt domain 정의를 읽어 배치 후보를 계산한다.

## 왜 Ansible과 분리하는가

Ansible의 역할은 선택된 노드에 원하는 상태를 적용하는 **프로비저너**다. 반면 scheduler의 역할은 여러 compute 중 하나를 고르고, 부족한 자원을 거절하며, 어떤 노드를 골랐는지 보여 주는 **의사결정**이다.

```text
사용자 요청
  → scheduler.py: compute의 현재 domain/메모리 확인 및 대상 선택
  → provision-instance.yml: 선택된 compute에 qcow2·cloud-init·libvirt 적용
  → DHCP: inner VM에 provider IP 할당
```

나중에 API와 MariaDB를 추가하면 scheduler는 요청 상태와 자원 reservation을 DB에 기록하고 worker에게 프로비저닝 작업을 전달한다. 이 도구는 그 이전 단계에서 동일한 경계와 호출 방식을 검증한다.

## 판단 기준

각 compute outer VM은 3 vCPU와 6GB RAM이지만, host OS와 libvirt에 자원을 남긴다. inventory에는 다음의 보수적 한도를 정의한다.

| 항목 | 노드당 배치 한도 |
|---|---:|
| vCPU | 2 |
| 메모리 | 4096MB |

scheduler는 정의된 모든 libvirt domain(켜진 VM과 꺼진 VM 모두)의 vCPU·메모리를 예약량으로 합산한다. 요청을 수용할 수 있는 노드 중 VM 수, 예약 메모리, 예약 vCPU가 가장 적은 노드를 선택한다. 또한 `/proc/meminfo`의 실제 가용 메모리가 요청량보다 512MB 이상 여유 있는지 검사한다.

이 방식은 단일 control 운영자 기준이다. 동시에 여러 요청이 들어올 때의 경쟁 조건은 DB reservation과 작업 큐를 추가하는 control-plane 단계에서 해결한다.

## 실행

먼저 검증 모드로 선택 결과만 확인한다. `demo-web01`이 compute1에 있으므로 다음 요청은 compute2가 선택되어야 한다.

```bash
cd ~/private-cloud-platform

python3 control-plane/scheduler/scheduler.py \
  --name demo-web02 \
  --vcpus 1 \
  --memory-mb 1024 \
  --disk-gb 10
```

출력이 맞으면 `--execute`로 Ansible 프로비저너를 호출한다.

```bash
python3 control-plane/scheduler/scheduler.py \
  --name demo-web02 \
  --vcpus 1 \
  --memory-mb 1024 \
  --disk-gb 10 \
  --execute
```

이 코드는 control의 `~/.ssh/private-cloud-ansible` 키와 `automation/ansible/inventory/hosts.yml`을 사용한다. 개인키·비밀번호·DHCP lease 파일은 Git에 저장하지 않는다.
