# GlusterFS 스토리지 설계와 운영 범위

## 현재 구성

이 플랫폼의 공유 스토리지는 NFS와 GlusterFS를 동시에 쓰지 않는다. **GlusterFS replica 2 하나**를
인스턴스 이미지와 qcow2 overlay의 공유 파일시스템으로 사용한다. NFS는 강의의 기본 예시이고, 이
프로젝트에서는 storage 가용성과 복구 과정을 보여 주기 위해 GlusterFS를 선택했다.

```text
storage1 (172.16.8.21) ── /dev/sdb 10GB ── /srv/gluster/brick1/instances
                                      ╲
                                       ╲ replica 2: instance-volumes
                                       ╱
storage2 (172.16.8.22) ── /dev/sdb 10GB ── /srv/gluster/brick1/instances

control, compute1, compute2
  └── /var/lib/private-cloud/volumes (GlusterFS FUSE client)
        ├── images/       # checksum 검증을 거친 GenericCloud base image
        └── instances/    # VM별 qcow2 overlay와 cloud-init seed
```

`configure-gluster-clients.yml`은 `storage1`을 primary volfile server, `storage2`를
`backupvolfile-server`로 `/etc/fstab`에 등록한다. 따라서 primary가 내려가도 client는 다른
volfile server로 mount 정보를 얻을 수 있다.

## 왜 NFS가 아닌가

NFS를 한 대에 구성하면 강의의 “공유 이미지 저장소” 요구를 가장 빨리 만족시킬 수 있다. 하지만 그
NFS 서버와 디스크는 단일 장애점이 된다. 이 프로젝트는 동일 기능을 GlusterFS replica 2로 구현해
두 brick에 사본을 두고, storage 장애 뒤 heal 상태까지 보여 주는 방향을 택했다.

GlusterFS는 **MariaDB의 복제나 DB HA 도구가 아니다.** MariaDB는 control node의 application
metadata source of truth이고, GlusterFS는 instance disk/image의 file storage다.

## 구현된 보호와 관측

| 항목 | 현재 구현 |
|---|---|
| 데이터 복제 | `instance-volumes` replica 2 |
| client 연결 | FUSE + primary/backup volfile server |
| 부팅 후 복구 | storage `glusterd`와 client mount를 systemd/fstab으로 자동 시작 |
| 접근 제한 | provider network `172.16.8.*`만 volume client로 허용 |
| 데이터 디스크 | OS disk와 분리된 `/dev/sdb`, XFS, UUID 기반 mount |
| 관찰 | Grafana brick 사용률, `StorageNodeDown`, `GlusterBrickCapacityHigh` alert rule |
| 운영 확인 | `gluster volume status`, `gluster volume heal ... info summary` |

## 장애와 복구에서 확인할 명령

control에서 실행한다.

```bash
ssh storage1 'sudo -n gluster peer status'
ssh storage1 'sudo -n gluster volume status instance-volumes'
ssh storage1 'sudo -n gluster volume heal instance-volumes info summary'
findmnt -T /var/lib/private-cloud/volumes
```

storage 한 대를 VMware에서 정지하는 시연은 inner VM을 정지하거나 snapshot을 남긴 상태에서만 한다.
복구 뒤에는 `glusterd`가 올라온 후 heal summary가 0으로 수렴하는지 확인한다. 이 시연은
degraded/readiness와 self-heal을 보이는 것이며, 쓰기 부하 중 임의 장애 주입을 권장하는 절차가 아니다.

## 의도적으로 미구현인 HA 범위

현재 2-node replica는 두 data copy를 제공하지만 split-brain 방지, fencing, quorum을 갖춘 완전한 HA가
아니다. 또한 client mount가 살아 있는 것과 workload의 모든 I/O가 안전하게 계속되는 것은 다른 문제다.

다음 단계는 `storage3`를 **arbiter node**로 추가해 replica 3 arbiter 1 volume으로 전환하고,
quorum·fencing·운영 절차를 함께 설계하는 것이다. arbiter는 주로 metadata를 저장해 data brick보다
작은 디스크로 둘 수 있지만, 기존 VM 디스크가 든 volume의 layout을 바꾸는 작업은 반드시 snapshot,
maintenance window, restore 검증을 전제로 한다. 오늘의 제출 범위에서 실행 중인 volume을 즉석 전환하지
않는 이유다.

이후 실제 production 수준으로 확장한다면 storage VM을 서로 다른 physical host/rack/power domain에
분리하고, MariaDB control-plane HA와 compute workload migration을 별도 과제로 다뤄야 한다.
