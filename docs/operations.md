# 운영과 관찰 가능성

## 웹 접속과 HTTPS 배포

- 포털: `https://cloud.lab.test` (기존 admin/member 계정)
- 운영자 Grafana: `https://grafana.lab.test` (기존 Grafana 계정, 별도 로그인)
- Nginx: `172.16.8.10:443`. 기존 `172.16.2.10:8080`, `:3000` 직접 접속은 사용하지 않는다.
- 방화벽은 VMnet8의 Windows 호스트 `172.16.8.1/32`만 HTTPS에 허용한다. VM 네트워크, DHCP, GlusterFS 구성은 유지한다.

control의 저장소에 코드를 동기화한 뒤 다음 두 playbook을 순서대로 실행한다.

```bash
cd ~/private-cloud-platform/automation/ansible
ansible-playbook --ask-become-pass --limit control playbooks/configure-control-api.yml
ansible-playbook --ask-become-pass --limit control playbooks/configure-monitoring.yml
```

첫 playbook은 실습 CA/서버 인증서, control의 hosts, Nginx, Secure 세션 쿠키를 구성한다.
두 번째는 Grafana의 loopback/HTTPS 주소와 Slack 대시보드 링크를 맞춘다.
CA 개인키는 `/etc/private-cloud/pki/root-ca.key`, 서버 개인키는
`/etc/pki/nginx/private-cloud/server.key`에 root 전용으로 보관한다. Git에 넣지 않는다.
공유 가능한 CA 공개 인증서는 `/etc/pki/ca-trust/source/anchors/private-cloud-lab.crt`다.
CA는 5년, 서버 인증서는 1년 유효하며, 서버 인증서는 만료 30일 이내 playbook 재실행 시 갱신한다.
자동 갱신 스케줄러는 없으며 CA 자체의 갱신은 PC 신뢰 재등록을 포함하는 별도 작업이다.

Windows에서는 공개 인증서를 SSH/SCP로 받은 뒤 아래 스크립트로 CurrentUser 신뢰 저장소와
`C:\Windows\System32\drivers\etc\hosts`의 프로젝트 블록만 등록한다.

```powershell
.\infra\vmware\scripts\Setup-LabWebClient.ps1 -CertificatePath '<CA 공개 인증서 경로>' -ExpectedSha256 '<SSH로 확인한 인증서 SHA-256 지문>'
```

hosts 변경 시 Windows 관리자 승인이 한 번 필요할 수 있다. 기존 hosts는 백업한다.
현재 PC 이외에서는 hosts/인증서만 복사해도 연결되지 않는다. 실제 LAN 접속은 별도 경로와
제한된 방화벽·포트 전달이 필요하며, 이 스크립트는 이를 구성하지 않는다. VM SSH 접속 경로도 별도다.
Slack 링크 역시 해당 이름 해석과 네트워크 접근이 가능한 PC에서만 열린다.

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
| `ComputeNodeDown` | compute exporter 수집 실패가 30초 지속 | hypervisor와 해당 guest 영향 확인 |
| `StorageNodeDown` | storage exporter 수집 실패가 30초 지속 | GlusterFS replica degraded 가능성 |
| `ManagedInstanceExporterDown` | 수집 대상 guest exporter 실패가 30초 지속 | guest metrics endpoint 점검 |
| `GlusterBrickCapacityHigh` | brick 사용률 85% 초과가 10분 지속 | image·overlay 디스크 용량 증설 판단 |

실습용 빠른 알림: 수집·규칙 평가는 10초 주기, 수집 timeout은 5초다. 최초 전송 대기는
5초(`group_wait`), 기존 그룹의 변경·복구 확인 주기는 15초(`group_interval`)다.
첫 장애 알림은 대략 40~60초, exporter 응답 복구 후 복구 알림은 대략 10~30초를 예상한다.
이는 네트워크·Slack 지연과 재시도를 제외한 예상이며 보장 시간이 아니다. VM 부팅 시간도 별도다.
동일 장애가 계속되면 4시간 간격으로 반복한다. 짧은 순간 끊김은 30초 지속 조건으로 거른다.
규칙 테스트: `promtool test rules tests/monitoring/alert-timing.test.yml` (저장소 루트에서 실행).

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
- 향후 범위: Gluster arbiter/fencing, planned live migration, control-plane HA, multiple worker locking, CI, 실제 사내 DNS/PKI·접속망 연동.
