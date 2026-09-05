# 최종 시연 Runbook

## 목적과 범위

이 문서는 발표 직전에 "정상 상태 → 계획된 장애 → 관측/알림 → 복구"를 재현하기 위한 절차다.
현재 lab에서 검증하는 것은 **감지와 복구 확인**이며, compute 장애 시 다른 compute로 VM을 자동
migration/failover하는 기능은 포함하지 않는다. 이 한계를 명확하게 말하는 것이 실제 운영 관점에서도
정확하다.

모든 outer node가 한 VMware Workstation 호스트에서 실행되므로, 이 lab은 물리 서버·전원·ToR 장애
도메인이 분리된 production HA 환경도 아니다.

## 발표에서 보여 줄 설계 요약

```text
Portal request
  → MariaDB: instance + operation + event를 transaction으로 기록
  → worker: scheduler가 compute 선택
  → Ansible/libvirt: inner VM 생성 또는 삭제
  → Prometheus: outer node와 opt-in inner VM 지표 수집
  → Alertmanager: 지속 장애를 Slack으로 전달
```

| 영역 | 현재 구현 | 시연에서 말할 점 |
|---|---|---|
| 데이터베이스 | MariaDB + Alembic + FK + operation/event audit | API 요청과 실제 비동기 작업을 분리해 실패도 추적한다. |
| compute | compute1/2, KVM/libvirt, OVS | scheduler는 보수적 vCPU·메모리 예약량과 인스턴스 수를 비교한다. |
| storage | GlusterFS replica 2 | 한 storage brick 장애에서 사본 접근과 heal을 확인한다. full HA/fencing은 아니다. |
| monitoring | Prometheus, Grafana, Alertmanager | Grafana는 추세/상태 화면, Alertmanager는 지속 장애의 Slack 통지 담당이다. |

## 사전 확인

control에서 실행한다.

```bash
systemctl is-active prometheus alertmanager grafana-server
curl -fsS http://127.0.0.1:9090/-/healthy
curl -fsS http://127.0.0.1:9093/-/healthy

ssh compute1 'sudo -n systemctl is-active libvirtd openvswitch'
ssh compute2 'sudo -n systemctl is-active libvirtd openvswitch'
ssh storage1 'sudo -n gluster volume status instance-volumes'
```

모두 `active` 또는 정상 status여야 한다. Prometheus의 현재 target도 확인한다.

```bash
curl -fsS 'http://127.0.0.1:9090/api/v1/query?query=up' \
  | python3 -m json.tool
```

## 시연 1 — compute 장애 감지와 부팅 후 복구

### 목표

`ComputeNodeDown` alert가 1분 이상 지속된 compute exporter 장애를 감지하고, VMware에서 해당
outer VM을 다시 부팅했을 때 Prometheus target이 `up=1`로 돌아오는 것을 확인한다.

### 절차

1. **영향 범위를 먼저 확인한다.**

   ```bash
   ssh compute1 'sudo -n virsh list --all'
   ssh compute2 'sudo -n virsh list --all'
   ```

   실행 중 inner VM이 있는 compute를 끌 경우 그 VM도 함께 멈춘다. 발표용 테스트에서는 영향이
   작은 compute를 고르거나, 영향을 명시한 계획된 장애로 진행한다.

2. Grafana의 `Private Cloud Nodes` dashboard를 열어 대상 compute의 CPU·메모리·`up` 상태가
   정상임을 캡처한다.
3. VMware Workstation에서 대상 compute outer VM을 **Power Off** 한다.
4. 75–90초 기다린다. Prometheus scrape interval과 alert의 `for: 1m`을 합친 시간이다.
5. Grafana에서 대상 node가 down인 것을 확인하고 Slack에서 `ComputeNodeDown` 메시지를 확인한다.
6. VMware에서 같은 outer VM을 다시 **Power On** 한다.
7. 30–90초 뒤 `up=1`과 Slack의 resolved 메시지를 확인한다.

   ```bash
   curl -fsS 'http://127.0.0.1:9090/api/v1/query?query=up%7Bjob%3D%22node%22%2Crole%3D%22compute%22%7D' \
     | python3 -m json.tool
   ssh compute1 'sudo -n systemctl is-active libvirtd openvswitch'
   ```

### 정확한 해석

`libvirtd`와 OVS가 enabled 상태라 outer VM 재부팅 뒤 자동으로 살아난다. `virt-install`로 생성한
inner VM에는 autostart도 설정되어 있다. 그러나 이는 **같은 compute에서의 재기동**이지,
compute1 장애 때 compute2로 자동 이동시키는 HA/failover가 아니다.

## 시연 2 — inner VM monitoring 경로

### 목표

owner가 monitoring을 선택한 inner VM의 node exporter 수집 실패를 `ManagedInstanceExporterDown`
alert로 구분해 확인한다.

### 절차

1. Portal에서 monitoring enabled인 VM을 선택하고 Prometheus target이 `up=1`인지 확인한다.
2. 그 VM에 owner key로 SSH 접속해 exporter만 중지한다.

   ```bash
   sudo systemctl stop node_exporter
   ```

3. 2분 이상 기다린 뒤 portal monitoring 화면의 수집 상태와 Slack alert를 확인한다.
4. 다음 명령으로 되돌리고 resolved alert를 확인한다.

   ```bash
   sudo systemctl start node_exporter
   ```

이 테스트는 VM을 실제로 종료하지 않고 **관측 경로의 장애**만 검증한다. exporter down은 VM 자체가
반드시 꺼졌다는 뜻은 아니므로, 발표에서도 "guest metrics endpoint unreachable"이라고 설명한다.

## 시연 3 — GlusterFS replica 2의 degraded/heal 확인

### 안전 조건

GlusterFS는 inner VM qcow2 디스크를 저장한다. 쓰기 중 storage 노드를 강제로 끄는 것은 데이터
일관성 검증이 아니라 장애 주입이므로, 발표 전 VM을 정지하거나 snapshot을 남긴 뒤 진행한다.

### 절차

1. 정상 상태를 기록한다.

   ```bash
   ssh storage1 'sudo -n gluster volume status instance-volumes'
   ssh storage1 'sudo -n gluster volume heal instance-volumes info summary'
   ```

2. VMware에서 `storage2`를 Power Off한다.
3. control에서 마운트 자체가 남아 있는지 읽기만 확인한다.

   ```bash
   findmnt -T /var/lib/private-cloud/volumes
   ls -la /var/lib/private-cloud/volumes/images
   ssh storage1 'sudo -n gluster volume status instance-volumes'
   ```

4. `storage2`를 Power On하고 Gluster 서비스가 올라올 때까지 기다린다.
5. heal 상태가 0으로 수렴하는 것을 확인한다.

   ```bash
   ssh storage1 'sudo -n gluster peer status; sudo -n gluster volume heal instance-volumes info summary'
   ```

### 정확한 해석

replica 2는 데이터 사본을 두 노드에 둔다. 하지만 network partition의 split-brain, fencing, quorum을
해결하는 완전한 HA 구성이 아니다. storage3 arbiter 또는 3-way replica와 fencing은 다음 개선 단계로
명시한다. MariaDB는 control에 단일 노드로 존재하므로, 이 storage 장애 테스트는 DB failover 테스트가
아니다.

## DB 시연 증거

Portal에서 VM 하나를 생성·삭제한 뒤 control에서 다음 질의를 실행한다.

```bash
sudo mariadb private_cloud
```

```sql
SELECT i.name, i.status, c.name AS compute, i.provider_ip, i.deleted_at
FROM instances AS i
LEFT JOIN compute_nodes AS c ON c.id = i.assigned_compute_id
ORDER BY i.created_at DESC;

SELECT o.operation_type, o.status, o.attempts, o.error_message, o.created_at, o.completed_at
FROM operations AS o
JOIN instances AS i ON i.id = o.instance_id
ORDER BY o.created_at DESC
LIMIT 10;

SELECT i.name, e.previous_status, e.next_status, e.message, e.created_at
FROM instance_events AS e
JOIN instances AS i ON i.id = e.instance_id
ORDER BY e.id DESC
LIMIT 20;
```

발표 핵심은 “VM 목록 하나만 저장한 DB”가 아니라, 요청(`operations`)과 상태 전이(`instance_events`)를
별도 테이블로 남겨 실패·재시도·감사가 가능하도록 설계했다는 점이다. schema, FK, soft delete는
[데이터 모델 문서](data-model.md)에서 근거를 보여 줄 수 있다.

## PPT 최소 구성

1. 문제와 목표: VMware 위 소형 IaaS control plane.
2. 구성도: control/compute/storage/provider network.
3. 생성 흐름: portal → DB operation → worker/scheduler → Ansible/libvirt.
4. DB ERD와 선택 이유: FK, queue, audit, soft delete.
5. 보안: key injection, private key 미보관, API·Prometheus loopback, secrets root-only.
6. 관측과 장애 시연: Grafana/Slack, compute down/recovery, Gluster heal.
7. 한계와 roadmap: single MariaDB, replica2의 split-brain, actual migration/failover 미구현.
