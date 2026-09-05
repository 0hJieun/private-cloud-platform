# 첫 KVM 인스턴스 프로비저닝

이 문서는 control이 GenericCloud 베이스 이미지, cloud-init, libvirt를 연결해 inner VM 한 대를 만드는 흐름을 설명한다. 첫 검증에서는 사용자가 compute를 명시한다. 이후 control-plane scheduler가 자원을 비교해 compute를 선택하고 같은 프로비저너를 호출한다.

## 구성 흐름

```text
control의 Ansible
  └── compute1 또는 compute2
       ├── GlusterFS: base qcow2 → 인스턴스별 qcow2 overlay 생성
       ├── cloud-init: CIDATA seed.img 생성
       └── libvirt: OVS br-provider에 연결된 KVM domain 부팅
            └── control의 DHCP에서 172.16.8.151~239 주소 할당
```

`disk.qcow2`는 읽기 전용 GenericCloud 베이스 이미지의 backing file을 참조한다. 따라서 각 인스턴스에는 운영 중 변경된 블록만 별도로 저장된다. 베이스 이미지는 수정하지 않으며, 인스턴스 삭제 전까지 overlay와 seed 파일을 보존한다.

`seed.img`는 `CIDATA` 라벨을 가진 NoCloud 디스크다. 최초 부팅 시 cloud-init이 여기서 hostname, `user1` 계정, control의 Ansible 공개키를 읽는다. 비밀번호 SSH 접속과 root SSH 접속은 사용하지 않는다. 로컬 실습에서 초기 구성 자동화를 위해 `user1`에 passwordless sudo를 부여하며, 운영 환경에서는 별도 권한 정책과 키 교체 정책을 적용한다.

## 실행 예시

control에서 다음을 실행하면 `demo-web01`을 `compute1`에 1 vCPU, 1GB RAM으로 생성한다.

```bash
cd ~/private-cloud-platform/automation/ansible

# 공유 GlusterFS 위의 qcow2를 QEMU가 접근하도록 SELinux 정책을 적용한다.
ansible-playbook playbooks/configure-compute-runtime.yml

# 첫 검증은 scheduler 대신 대상 compute를 명시한다.
ansible-playbook \
  --limit compute1 \
  -e instance_name=demo-web01 \
  playbooks/provision-instance.yml
```

VM이 DHCP lease를 받은 뒤 control에서 다음과 같이 접속할 수 있다. `<DHCP_IP>`는 control DHCP 풀 범위의 할당 주소다.

```bash
ssh -i ~/.ssh/private-cloud-ansible user1@<DHCP_IP>
```

## 검증

compute에서 domain과 OVS 연결을 확인한다.

```bash
sudo virsh -c qemu:///system list --all
sudo virsh -c qemu:///system domiflist demo-web01
```

control에서 DHCP 서버 상태와 lease 기록을 확인한다.

```bash
sudo systemctl is-active dhcpd
sudo grep -A 12 -B 2 'client-hostname "demo-web01"' /var/lib/dhcpd/dhcpd.leases
```

## 다음 단계

이 playbook은 **프로비저너**다. 대상 compute를 고르는 scheduler, 생성 상태를 MariaDB에 기록하는 API, IP를 dynamic inventory로 변환하는 worker는 control-plane 단계에서 추가한다. 이를 분리하면 스케줄링 판단과 실제 VM 생성 작업을 독립적으로 재시도·감사할 수 있다.
