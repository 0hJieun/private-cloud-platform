# Architecture

## Networks

| Network | Purpose | Example range |
|---|---|---|
| vmnet2 | management | `172.16.100.0/24` |
| vmnet8 | provider/instance | `172.16.8.0/24` |

The VMware DHCP service is disabled on networks managed by the control node.

## Responsibilities

- `control`: API, scheduler, MariaDB, DHCP, Ansible, Prometheus, Grafana
- `compute1`, `compute2`: libvirt/KVM and Open vSwitch
- `storage`: NFS image repository and backup target
- `storage1`, `storage2`: GlusterFS data nodes

## Instance lifecycle

```text
REQUESTED → SCHEDULING → IMAGE_PREPARING → CREATING
→ WAITING_FOR_IP → CONFIGURING → ACTIVE
```

Failure paths and cleanup rules will be documented as they are implemented.
