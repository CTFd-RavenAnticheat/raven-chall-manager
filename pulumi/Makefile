# Minimal Pulumi Deployment for Chall-Manager
# Mirrors your Docker Compose setup

.PHONY: all deploy update destroy status logs port-forward

STACK ?= prod
NAMESPACE ?= chall-manager

check:
	@if ! command -v pulumi >/dev/null 2>&1; then \
		echo "❌ Pulumi not installed. Run: curl -fsSL https://get.pulumi.com | sh"; \
		exit 1; \
	fi
	@if ! kubectl cluster-info >/dev/null 2>&1; then \
		echo "❌ kubectl not connected to cluster"; \
		exit 1; \
	fi

# Minimal deployment matching Docker Compose
all: check
	@echo "==> Deploying chall-manager (minimal setup)..."
	@cd ../deploy && \
		pulumi stack select $(STACK) --create 2>/dev/null || true && \
		pulumi config set namespace $(NAMESPACE) && \
		pulumi config set replicas 1 && \
		pulumi config set pvc-storage-size 10Gi && \
		pulumi config set tag v3 && \
		pulumi config set janitor.mode ticker && \
		pulumi config set janitor.ticker 1m && \
		pulumi config set limits.cpu 2.0 && \
		pulumi config set limits.memory 4Gi
	@echo ""
	@echo "⚠️  Please configure OCI credentials:"
	@echo "   cd ../deploy && pulumi config set oci.username YOUR_USERNAME"
	@echo "   cd ../deploy && pulumi config set --secret oci.password YOUR_PASSWORD"
	@echo ""
	@echo "Then run: make deploy"

# Deploy after OCI is configured
deploy: check
	@echo "==> Deploying to stack '$(STACK)'..."
	@cd ../deploy && pulumi up --stack $(STACK)
	@echo ""
	@echo "✅ Deployment complete!"
	@echo ""
	@echo "Access: kubectl port-forward -n $(NAMESPACE) svc/chall-manager 8080:8080"

# Update deployment
update: check
	@cd ../deploy && pulumi up --stack $(STACK)

# Preview changes
preview: check
	@cd ../deploy && pulumi preview --stack $(STACK)

# Destroy everything
destroy: check
	@echo "⚠️  This will DELETE all resources!"
	@read -p "Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ] || exit 1
	@cd ../deploy && pulumi destroy --stack $(STACK)

# Quick status
status:
	@kubectl get pods -n $(NAMESPACE) 2>/dev/null || echo "Namespace $(NAMESPACE) not found"

# View logs
logs:
	@kubectl logs -n $(NAMESPACE) -l app.kubernetes.io/name=chall-manager -f --tail=100

# Port forward
port-forward:
	@echo "Forwarding localhost:8080 to chall-manager..."
	@kubectl port-forward -n $(NAMESPACE) svc/chall-manager 8080:8080

# Configure OCI interactively
config-oci:
	@echo "OCI Registry Configuration"
	@read -p "Username: " user; \
	cd ../deploy && pulumi config set oci.username "$$user"
	@read -s -p "Password: " pass; echo; \
	cd ../deploy && pulumi config set --secret oci.password "$$pass"
	@echo "✅ OCI credentials configured"

help:
	@echo "Minimal Pulumi Deployment for Chall-Manager"
	@echo ""
	@echo "Quick start:"
	@echo "  make all          # Initial setup (configure OCI after)"
	@echo "  make config-oci   # Set OCI credentials"
	@echo "  make deploy       # Deploy everything"
	@echo ""
	@echo "Operations:"
	@echo "  make update       # Update deployment"
	@echo "  make preview      # Preview changes"
	@echo "  make status       # Check pod status"
	@echo "  make logs         # View logs"
	@echo "  make port-forward # Access on localhost:8080"
	@echo "  make destroy      # Remove everything"
	@echo ""
	@echo "Environment:"
	@echo "  STACK=prod        # Pulumi stack name"
	@echo "  NAMESPACE=cm      # Kubernetes namespace"
