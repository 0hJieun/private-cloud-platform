# 운영과 관찰 가능성

## 관측 경계

| 대상 | 수집 방식 | 열람 주체 | 목적 |
|---|---|---|---|
| control·compute·storage | node exporter → Prometheus | admin Grafana | 노드 자원, hypervisor, Gluster brick 상태 |
| control plane | MariaDB operation/event, API health | admin portal | 요청 처리와 worker 상태 추적 |
| monitoring opt-in instance | guest node exporter → Prometheus HTTP discovery | 소유자 portal, admin | 해당 guest의 CPU·메모리·디스크·네트워크 |

Grafana는 운영자용 분석 도구다. member에게 Grafana datasource를 직접 열지 않고, portal API가
소유자 검증 뒤 해당 instance ID에 고정된 PromQL 결과만 반환한다.

## Alertmanager와 Slack

Prometheus가 alert rule을 평가하고, control의 loopback Alertmanager(`127.0.0.1:9093`)가
grouping·해결 알림·Slack 전송을 담당한다. Webhook URL은 Git, systemd unit, Ansible 출력에 넣지 않고
`/etc/private-cloud/alertmanager.env`(`root:root`, `0600`)에서만 읽는다.

| Alert | 조건 | 운영 의미 |
|---|---|---|
| `ComputeNodeDown` | compute exporter가 1분 이상 down | hypervisor와 해당 guest 영향 확인 |
| `StorageNodeDown` | storage exporter가 1분 이상 down | GlusterFS replica degraded 가능성 |
| `ManagedInstanceExporterDown` | opt-in guest exporter가 2분 이상 down | guest metrics endpoint 점검 |
| `GlusterBrickCapacityHigh` | brick 사용률 85% 초과가 10분 지속 | image·overlay 디스크 용량 증설 판단 |

`ManagedInstanceExporterDown`은 VM domain이 반드시 꺼졌다는 뜻이 아니라 exporter·네트워크·firewall을
포함한 관측 경로가 끊겼다는 신호다. domain lifecycle까지 엄밀하게 판단하려면 libvirt exporter 또는
control-plane reconcile을 추가해야 한다.

## GlusterFS 스토리지

NFS와 GlusterFS를 같이 쓰지 않는다. 이 프로젝트의 공유 스토리지는 `instance-volumes`라는
**GlusterFS replica 2** 단일 볼륨이다.

```text
storage1 172.16.8.21  /dev/sdb → /srv/gluster/brick1/instances
                         ╲       replica 2: instance-volumes
                          ╱
storage2 172.16.8.22  /dev/sdb → /srv/gluster/brick1/instances

control·compute1·compute2 → /var/lib/private-cloud/volumes (FUSE client)
```

`storage1`은 primary volfile server, `storage2`는 backup volfile server다. GenericCloud base images와
VM별 qcow2 overlay는 이 공유 볼륨에 저장한다. GlusterFS는 파일/VM 디스크 스토리지이며, control의
MariaDB application metadata를 복제하거나 HA로 만드는 도구는 아니다.

클라이언트의 `/etc/fstab`은 `_netdev,nofail,x-systemd.automount`와 backup volfile server를 함께 사용한다.
따라서 control·compute가 storage보다 먼저 부팅되어도 부팅 자체는 막지 않고, 해당 경로를 처음 접근할 때
두 storage 주소로 다시 마운트를 시도한다.

### 부팅 순서 역전 검증 (2026-09-06, KST)

기존 VM 두 대를 정상 종료하고 worker를 일시 정지한 뒤, storage 두 대를 끈 상태에서
compute1을 먼저 부팅했다. VM 자동 시작은 이 시험에서 잠시 해제했다.

| 시각 | 시험 | 관찰 결과 |
|---|---|---|
| 11:40:26 | storage 없이 compute1 부팅 | multi-user target 도달, SSH 가능, automount 대기 |
| 11:40:45–54 | 공유 `images` 경로 접근 | 9초 후 접근 실패, mount unit 실패, automount는 대기 유지 |
| 11:41:57 | storage 두 대 복구 후 같은 경로 재접근 | 수동 mount·서비스 재시작 없이 FUSE 마운트와 파일 조회 성공 |
| 복구 후 | 기존 VM·worker 재개 | vm01·vm02 SSH 접속, vm02 autostart 재설정, compute1 실패 unit 0개 |

이는 계속 polling하는 방식이 아니라 **경로 재접근이 마운트를 다시 요청하는 방식**이다.
스토리지가 없는 동안 파일 작업은 실패할 수 있고 mount 실패로 systemd가 degraded를 표시할 수 있다.
실패한 VM 생성 요청이나 VM autostart를 자동 재실행한다는 뜻은 아니다.

이 시험에서 automount 활성화 뒤 `findmnt` 결과에 `autofs`와 `fuse.glusterfs`가 함께 나오는 것도 확인했다.
VM 생성·삭제와 이미지 준비의 공통 사전 검사는 경로 접근으로 자동 마운트를 요청한 뒤,
정확한 mountpoint에서 `fuse.glusterfs`만 선택해 검증한다. 로컬 디렉터리나 autofs만 남은 상태는 통과시키지 않는다.
수정한 playbook 5개의 문법 검사, 두 compute의 실제 공유 마운트 검사, 임시 automount 경로의
첫 접근 시 마운트 성공, 일반 로컬 경로의 검사 실패까지 확인했다. 임시 마운트와 unit은 시험 후 제거했다.

정상·복구 확인은 control에서 다음처럼 한다.

```bash
ssh storage1 'sudo -n gluster peer status'
ssh storage1 'sudo -n gluster volume status instance-volumes'
ssh storage1 'sudo -n gluster volume heal instance-volumes info summary'
findmnt -T /var/lib/private-cloud/volumes
```

2-node replica는 data copy를 제공하지만 quorum, fencing, split-brain 방지까지 갖춘 완전한 HA는 아니다.
`storage3` arbiter 전환은 기존 VM disk volume의 layout 변경을 수반하므로 snapshot·maintenance window·restore
test를 전제로 하는 다음 단계로 둔다.

## 시연에서 정확히 말할 한계

- compute outer VM을 다시 부팅하면 `libvirtd`와 OVS가 시작되고 autostart domain의 시작을 시도한다.
  이때 공유 스토리지가 준비되지 않았다면 domain 시작은 실패할 수 있으며 별도 재시도가 필요하다.
- 이는 compute1 장애 시 compute2로 자동 이동하는 migration/failover가 아니다.
- 모든 outer VM이 같은 VMware Workstation host에 있으므로 물리 장애 도메인이 분리된 production HA가 아니다.
- 향후 범위: Gluster arbiter/fencing, planned live migration, control-plane HA, multiple worker locking, TLS/CI.
