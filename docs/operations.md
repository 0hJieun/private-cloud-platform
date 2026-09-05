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

- compute outer VM을 다시 부팅하면 `libvirtd`, OVS, autostart domain이 같은 compute에서 복구된다.
- 이는 compute1 장애 시 compute2로 자동 이동하는 migration/failover가 아니다.
- 모든 outer VM이 같은 VMware Workstation host에 있으므로 물리 장애 도메인이 분리된 production HA가 아니다.
- 향후 범위: Gluster arbiter/fencing, planned live migration, control-plane HA, multiple worker locking, TLS/CI.
