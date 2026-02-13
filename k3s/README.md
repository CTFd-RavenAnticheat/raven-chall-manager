# K3s Multi-Node Cluster for Chall-Manager

This setup creates a scalable Kubernetes cluster using k3s (lightweight Kubernetes) that can span multiple VMs for horizontal scaling of CTF challenges.

## Architecture

```
VM1 (Control Plane + Worker)
├── k3s server (control plane components)
├── NFS server (for pcap storage)
├── MetalLB (LoadBalancer for services)
├── Traefik (Ingress controller)
└── Challenge pods

VM2, VM3, ... (Workers only)
├── k3s agent
└── Challenge pods
```

## Prerequisites

- 2+ VMs with network connectivity between them
- VMs running Ubuntu, Debian, Arch, CentOS, RHEL, or Fedora
- SSH access to all VMs
- Root/sudo access
- 4GB+ RAM per VM (8GB+ recommended for workers)

## Quick Start

### 1. Setup Control Plane (VM1)

On your first VM (the one that will be the control plane):

```bash
cd /mnt/storage/claude-cm/chall-manager/k3s

# Full automated setup
make all

# Or step by step:
make nfs        # Install NFS server
make server     # Install k3s control plane
make metallb    # Install MetalLB
make storage    # Install NFS provisioner and create PVC
make kubeconfig # Setup kubeconfig for your user
```

### 2. Add Worker Nodes (VM2, VM3, ...)

Get the join command from the control plane:

```bash
# On VM1
make worker-join-cmd
```

This will output something like:
```
curl -sfL https://get.k3s.io | K3S_URL=https://192.168.1.100:6443 K3S_TOKEN=K10xxxxx::server:xxxxx sh -
```

Run this command on each worker VM.

Alternatively, use the Makefile:

```bash
# On worker VM
export K3S_URL=https://<VM1_IP>:6443
export K3S_TOKEN=<token from VM1>
make join-worker
```

### 3. Verify Cluster

```bash
make status
```

You should see all nodes in "Ready" state.

## Configuration Details

### Storage

- **NFS Server**: Runs on the control plane VM
- **Export Path**: `/srv/nfs/k8s`
- **StorageClass**: `nfs-rwx` (ReadWriteMany)
- **PVC**: `pcap-core` (30Gi, shared across all nodes)

### Networking

- **Pod CIDR**: 10.42.0.0/16 (k3s default)
- **Service CIDR**: 10.43.0.0/16 (k3s default)
- **MetalLB**: Exposes LoadBalancer services on the control plane IP
- **Traefik**: Runs as LoadBalancer on ports 80/443

### Resource Settings

The k3s server is installed with:
- `--disable=traefik`: We install our own Traefik
- `--disable=servicelb`: We use MetalLB instead
- `--tls-san=<IP>`: Allows API access via IP

## Migrating from Kind

### 1. Backup Current State

On your old kind setup:

```bash
# Save list of running challenges
kubectl get deployments -A -l chall-manager.ctfer.io/challenge -o yaml > challenges-backup.yaml

# Note any custom configurations
kubectl get configmaps -A
kubectl get secrets -A
```

### 2. Setup K3s Cluster

Follow the Quick Start above to set up the new k3s cluster.

### 3. Update Chall-Manager

If running chall-manager in Docker:

```bash
# Stop old chall-manager
docker stop chall-manager
docker rm chall-manager

# Copy kubeconfig from k3s control plane
scp root@<VM1_IP>:/etc/rancher/k3s/k3s.yaml ~/.kube/k3s-config

# Update kubeconfig to use VM1 IP
sed -i 's/127.0.0.1/<VM1_IP>/g' ~/.kube/k3s-config

# Start chall-manager with new kubeconfig
docker run -d \
  --name chall-manager \
  --network host \
  -v ~/.kube/k3s-config:/root/.kube/config:ro \
  -v /var/lib/chall-manager:/tmp/chall-manager \
  ctferio/chall-manager:latest
```

### 4. Update Scenarios

Rebuild your challenge scenarios with the updated SDK (minimum resource requests):

```bash
cd /path/to/challenge-scenarios
# Update go.mod to use local SDK or rebuild with new SDK
pulumi up
```

### 5. Cleanup Old Cluster

```bash
cd /mnt/storage/claude-cm/chall-manager/kind
make clean
```

## Scaling

### Add More Workers

```bash
# Get current token
ssh root@<VM1_IP> 'cat /var/lib/rancher/k3s/server/node-token'

# On new worker VM
curl -sfL https://get.k3s.io | K3S_URL=https://<VM1_IP>:6443 K3S_TOKEN=<token> sh -
```

### Remove a Worker

```bash
# On the worker VM you want to remove
/usr/local/bin/k3s-agent-uninstall.sh

# On control plane, remove the node
kubectl delete node <worker-node-name>
```

## Troubleshooting

### Nodes Not Ready

```bash
# Check node status
kubectl describe node <node-name>

# Check k3s logs
sudo journalctl -u k3s -f

# On worker:
sudo journalctl -u k3s-agent -f
```

### NFS Not Working

```bash
# Check NFS exports on control plane
sudo exportfs -v

# Test NFS mount from worker
sudo apt install nfs-common
showmount -e <VM1_IP>

# Check NFS provisioner logs
kubectl logs -n default -l app=nfs-subdir-external-provisioner
```

### MetalLB Not Assigning IPs

```bash
# Check MetalLB pods
kubectl get pods -n metallb-system

# Check logs
kubectl logs -n metallb-system -l component=controller

# Verify IP pool config
kubectl get ipaddresspools -n metallb-system -o yaml
```

### Chall-Manager Can't Connect

```bash
# Verify kubeconfig
cat ~/.kube/config | grep server

# Test connection
kubectl get nodes

# If using Docker for chall-manager, ensure network connectivity
docker exec chall-manager kubectl get nodes
```

## Advanced Configuration

### Multiple Control Planes (HA)

For high availability with multiple control planes:

```bash
# On first server (already done)
# Note: Must use --cluster-init instead of default

# On additional servers:
curl -sfL https://get.k3s.io | K3S_TOKEN=<token> sh -s - server \
  --server https://<first-server-ip>:6443 \
  --disable=traefik \
  --disable=servicelb \
  --tls-san=<VIP_OR_LB_IP>
```

### Custom CIDRs

```bash
# Install with custom CIDRs
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="\
  server \
  --disable=traefik \
  --disable=servicelb \
  --cluster-cidr=10.42.0.0/16 \
  --service-cidr=10.43.0.0/16 \
  --cluster-dns=10.43.0.10" sh -
```

### Air-Gapped Installation

Download binaries first:
```bash
# Download k3s binary
wget https://github.com/k3s-io/k3s/releases/download/v1.29.0%2Bk3s1/k3s
chmod +x k3s
sudo cp k3s /usr/local/bin/

# Run installer with air-gap flags
INSTALL_K3S_SKIP_DOWNLOAD=true make server
```

## Makefile Targets

| Target | Description |
|--------|-------------|
| `all` | Full setup: NFS, k3s, MetalLB, storage |
| `nfs` | Install and configure NFS server |
| `server` | Install k3s control plane |
| `metallb` | Install MetalLB |
| `storage` | Install NFS provisioner and create PVC |
| `traefik` | Install Traefik ingress controller |
| `kubeconfig` | Copy kubeconfig for current user |
| `worker-join-cmd` | Show command to join worker nodes |
| `join-worker` | Join this node as a worker (set K3S_URL and K3S_TOKEN) |
| `status` | Show cluster status |
| `clean` | Remove everything |
| `help` | Show help |

## Security Notes

- k3s API server is exposed on port 6443
- Default kubeconfig has admin privileges
- NFS export is world-writable (for simplicity)
- Consider:
  - Restricting NFS exports to specific IPs
  - Using TLS for API server
  - Setting up proper RBAC
  - Network policies for challenge isolation

## References

- [K3s Documentation](https://docs.k3s.io/)
- [MetalLB Documentation](https://metallb.universe.tf/)
- [NFS Subdir External Provisioner](https://github.com/kubernetes-sigs/nfs-subdir-external-provisioner)
