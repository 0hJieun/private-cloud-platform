#!/usr/bin/env bash
set -Eeuo pipefail

# 이 스크립트는 Packer가 마지막으로 실행한다.
# 복제 직후 control의 Ansible이 user1@172.16.2.100으로 접속할 수 있도록
# 초기 관리 네트워크와 user1의 공개키는 유지한다.

dnf clean all
rm -rf /var/cache/dnf/*
rm -rf /tmp/* /var/tmp/*
rm -f /root/ks-post.log

# 각 복제본은 첫 부팅에서 고유 machine-id를 생성한다.
truncate -s 0 /etc/machine-id
rm -f /var/lib/dbus/machine-id
printf '%s\n' 'localhost.localdomain' > /etc/hostname

# Packer의 SSH 세션은 빌드가 끝날 때까지 유지해야 한다.
# 따라서 계정 삭제는 기반 이미지가 아닌 복제본의 첫 부팅에 한 번만 수행한다.
install -d -m 0755 /var/lib/private-cloud
touch /var/lib/private-cloud/remove-packer-user

cat > /usr/local/sbin/remove-packer-user-on-first-boot <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail

rm -f /etc/sudoers.d/90-packer-build
rm -f /home/packer/.ssh/authorized_keys
userdel --force --remove packer || true

rm -f /var/lib/private-cloud/remove-packer-user
rm -f /etc/systemd/system/multi-user.target.wants/remove-packer-user.service
rm -f /etc/systemd/system/remove-packer-user.service
rm -f /usr/local/sbin/remove-packer-user-on-first-boot
rm -f /usr/local/sbin/cleanup-template
EOF
chmod 0755 /usr/local/sbin/remove-packer-user-on-first-boot

cat > /etc/systemd/system/remove-packer-user.service <<'EOF'
[Unit]
Description=Remove the Packer build account on the first cloned boot
ConditionPathExists=/var/lib/private-cloud/remove-packer-user
Before=sshd.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/remove-packer-user-on-first-boot

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
# enable만 실행한다. --now를 붙이면 Packer의 현재 SSH 세션이 끊긴다.
systemctl enable remove-packer-user.service
