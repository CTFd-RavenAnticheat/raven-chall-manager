# Pulumi Deployment - Minimal

Deploy chall-manager inside Kubernetes (replaces Docker Compose).

## Quick Start (3 commands)

```bash
cd /mnt/storage/claude-cm/chall-manager/pulumi

# 1. Setup and configure
make all

# 2. Set OCI credentials
make config-oci

# 3. Deploy
make deploy
```

Or use the one-liner:

```bash
./deploy.sh
```

## What This Creates

```
Namespace: chall-manager
├── Deployment: chall-manager (1 replica, tag: v3)
├── Deployment: chall-manager-janitor (cleanup every 1m)
├── Service: chall-manager (ClusterIP:8080)
├── PVC: 10Gi (for /tmp/chall-manager data)
└── ServiceAccount (with RBAC permissions)
```

**vs Your Docker Compose:**
- ✅ No kubeconfig mounting needed
- ✅ Automatic restarts
- ✅ Native K8s service discovery
- ✅ Integrated janitor

## Usage

```bash
# Deploy
make deploy

# Check status
make status

# View logs
make logs

# Access locally
make port-forward  # http://localhost:8080

# Update
make update

# Destroy
make destroy
```

## Configuration

Edit in `../deploy`:

```bash
cd ../deploy

# View current config
pulumi config

# Change settings
pulumi config set tag v4
pulumi config set pvc-storage-size 20Gi
pulumi config set limits.cpu 4.0

# Update deployment
pulumi up
```

## Migration from Docker

```bash
# 1. Stop Docker container
docker stop chall-manager
docker rm chall-manager

# 2. Deploy to K8s
cd /mnt/storage/claude-cm/chall-manager/pulumi
./deploy.sh

# 3. Update scenarios
# Your scenarios now deploy to in-cluster chall-manager automatically
```

## Troubleshooting

```bash
# Pod not starting
kubectl describe pod -n chall-manager -l app.kubernetes.io/name=chall-manager

# PVC issues
kubectl get pvc -n chall-manager

# OCI auth failed
kubectl logs -n chall-manager -l app.kubernetes.io/name=chall-manager | grep -i oci
```
