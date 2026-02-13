#!/bin/bash
# Quickstart script for Pulumi chall-manager deployment
# Usage: ./quickstart.sh [stack-name]

set -e

STACK=${1:-prod}
NAMESPACE=${2:-chall-manager}

echo "=========================================="
echo "Chall-Manager Pulumi Quickstart"
echo "=========================================="
echo ""
echo "This will deploy chall-manager to your Kubernetes cluster."
echo "Stack: $STACK"
echo "Namespace: $NAMESPACE"
echo ""

# Check prerequisites
echo "==> Checking prerequisites..."

if ! command -v pulumi &> /dev/null; then
    echo "❌ Pulumi CLI not found. Installing..."
    curl -fsSL https://get.pulumi.com | sh
    export PATH=$PATH:$HOME/.pulumi/bin
fi

if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl not found. Please install kubectl first."
    exit 1
fi

if ! kubectl cluster-info &> /dev/null; then
    echo "❌ kubectl cannot connect to cluster. Please check your kubeconfig."
    exit 1
fi

echo "✅ All prerequisites met!"
echo ""

# Change to deploy directory
cd ../deploy

# Initialize stack
echo "==> Initializing Pulumi stack '$STACK'..."
pulumi stack select $STACK --create 2>/dev/null || pulumi stack select $STACK
echo "✅ Stack initialized!"
echo ""

# Configure basic settings
echo "==> Configuring basic settings..."
pulumi config set namespace $NAMESPACE
pulumi config set replicas 1
pulumi config set pvc-storage-size 10Gi
pulumi config set tag latest
pulumi config set registry ctferio
echo "✅ Basic configuration set!"
echo ""

# Configure resources
echo "==> Configuring resource limits..."
pulumi config set limits.cpu 2.0
pulumi config set limits.memory 4Gi
pulumi config set requests.cpu 0.5
pulumi config set requests.memory 1Gi
echo "✅ Resource limits set!"
echo ""

# Configure janitor
echo "==> Configuring janitor..."
pulumi config set janitor.mode ticker
pulumi config set janitor.ticker 1m
echo "✅ Janitor configured!"
echo ""

# OCI Registry configuration
echo "==> OCI Registry Configuration =="
echo "Enter your OCI registry username (for challenge images):"
read -r OCI_USER
pulumi config set oci.username "$OCI_USER"

echo "Enter your OCI registry password:"
read -rs OCI_PASS
echo ""
pulumi config set --secret oci.password "$OCI_PASS"
echo "✅ OCI registry configured!"
echo ""

# Preview deployment
echo "==> Previewing deployment..."
pulumi preview --stack $STACK
echo ""

# Deploy
echo "Ready to deploy!"
echo "This will create:"
echo "  - Namespace: $NAMESPACE"
echo "  - Deployment: chall-manager (1 replica)"
echo "  - Deployment: chall-manager-janitor"
echo "  - PVC: 10Gi storage"
echo ""
echo "Continue? (yes/no)"
read -r CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Deployment cancelled."
    exit 0
fi

echo ""
echo "==> Deploying chall-manager..."
pulumi up --stack $STACK --yes

echo ""
echo "=========================================="
echo "✅ Deployment Complete!"
echo "=========================================="
echo ""
echo "Outputs:"
pulumi stack output --stack $STACK
echo ""
echo "Status:"
kubectl get all -n $NAMESPACE
echo ""
echo "Access chall-manager:"
echo "  kubectl port-forward -n $NAMESPACE svc/chall-manager 8080:8080"
echo ""
echo "View logs:"
echo "  kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=chall-manager -f"
echo ""
echo "Next steps:"
echo "  1. Port forward: make -C ../pulumi port-forward"
echo "  2. Deploy challenges using the SDK"
echo "  3. Monitor: make -C ../pulumi logs"
echo ""
