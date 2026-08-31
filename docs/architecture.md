# Architecture

## Scope

The project is a small IaaS-style control plane running inside a VMware Workstation lab. VMware provides the outer lab environment; the platform being built consists of the control, compute, storage, and instance layers.

## Networks

| Network | Purpose | Example range |
|---|---|---|
| vmnet2 | management | `172.16.100.0/24` |
| vmnet8 | provider/instance | `172.16.8.0/24` |

The VMware DHCP service is disabled on networks managed by the control node.

## Components

- `control`: API, scheduler, MariaDB, DHCP, Ansible, Prometheus, Grafana, and administrator web application
- `compute1`, `compute2`: libvirt/KVM and Open vSwitch
- `storage`: NFS image repository and backup target
- `storage1`, `storage2`: GlusterFS data nodes
- instances: libvirt guests initialized with cloud-init and managed through Ansible

## Provisioning layers

```text
VMware Workstation
  └── outer lab VMs
      ├── Packer/image definitions
      └── Ansible host configuration

control plane
  └── libvirt instances
      ├── qcow2 volume preparation
      ├── cloud-init seed
      ├── DHCP lease discovery
      └── dynamic Ansible inventory
```

cloud-init initializes an instance after it boots. It is not the primary tool for creating VMware Workstation VMs. Outer VM image creation and guest configuration are handled by Packer and Ansible; the exact host-level VMware network setup remains environment-specific.

## Instance lifecycle

```text
REQUESTED → SCHEDULING → IMAGE_PREPARING → CREATING
→ WAITING_FOR_IP → CONFIGURING → ACTIVE
```

Errors must transition to `ERROR` and trigger cleanup of any partially created volume, lease, or database reservation.
