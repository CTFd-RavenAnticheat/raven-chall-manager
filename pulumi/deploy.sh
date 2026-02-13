#!/bin/bash
# One-command deployment matching your Docker Compose setup

set -e

STACK="${1:-prod}"
NAMESPACE="${2:-chall-manager}"

echo "🚀 Chall-Manager Pulumi Deployment"
echo "=================================="
echo ""

# Check tools
command -v pulumi >/dev/null 2>&1 || { echo "❌ Install Pulumi: curl -fsSL https://get.pulumi.com | sh"; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo "❌ Install kubectl"; exit 1; }
kubectl cluster-info >/dev/null 2>&1 || { echo "❌ kubectl not connected"; exit 1; }

# Configure
echo "📋 Configuring..."
cd ../deploy
pulumi stack select "$STACK" --create 2>/dev/null || true

# Minimal config matching your Docker setup
pulumi config set namespace "$NAMESPACE"
pulumi config set replicas 1
pulumi config set pvc-storage-size 10Gi
pulumi config set tag v3
pulumi config set janitor.mode ticker
pulumi config set janitor.ticker 1m
pulumi config set limits.cpu 2.0
pulumi config set limits.memory 4Gi

# OCI credentials
echo ""
echo "🔐 OCI Registry (for challenge images):"
read -p "Username: " oci_user
pulumi config set oci.username "$oci_user"
read -s -p "Password: " oci_pass
echo ""
pulumi config set --secret oci.password "$oci_pass"

# Deploy
echo ""
echo "🚀 Deploying..."
pulumi up --yes

echo ""
echo "✅ Done!"
echo ""
echo "Access: kubectl port-forward -n $NAMESPACE svc/chall-manager 8080:8080"
echo "Logs:   kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=chall-manager -f"
