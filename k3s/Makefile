# K3s Cluster Setup for Chall-Manager

.PHONY: all server workers nfs metallb traefik storage status clean

# Configuration
NFS_EXPORT_DIR := /srv/nfs/k8s
STORAGE_CLASS := nfs-rwx
SERVER_IP ?= $(shell ip route get 1 | awk '{print $$(NF-2); exit}')
K3S_TOKEN ?= $(shell sudo cat /var/lib/rancher/k3s/server/node-token 2>/dev/null || echo "NOT_YET_CREATED")
WORKER_IPS ?=

# OS Detection
OS_ID := $(shell . /etc/os-release 2>/dev/null && echo $$ID)
ifeq ($(OS_ID),ubuntu)
	NFS_PKG := nfs-kernel-server
	NFS_SERVICE := nfs-kernel-server
else ifeq ($(OS_ID),debian)
	NFS_PKG := nfs-kernel-server
	NFS_SERVICE := nfs-kernel-server
else ifeq ($(OS_ID),arch)
	NFS_PKG := nfs-utils
	NFS_SERVICE := nfs-server
else ifeq ($(OS_ID),centos)
	NFS_PKG := nfs-utils
	NFS_SERVICE := nfs-server
else ifeq ($(OS_ID),rhel)
	NFS_PKG := nfs-utils
	NFS_SERVICE := nfs-server
else ifeq ($(OS_ID),fedora)
	NFS_PKG := nfs-utils
	NFS_SERVICE := nfs-server
else
	$(error Unsupported OS: $(OS_ID). Supported: ubuntu, debian, arch, centos, rhel, fedora)
endif

all: nfs server metallb storage

# Setup NFS server on control plane
nfs:
	@echo "==> Installing NFS server on control plane..."
	@command -v exportfs >/dev/null 2>&1 || { \
		echo "Installing $(NFS_PKG)"; \
		sudo apt-get update && sudo apt-get install -y $(NFS_PKG) || \
		sudo yum install -y $(NFS_PKG) || \
		sudo pacman -S --needed --noconfirm $(NFS_PKG); \
	}
	@echo "==> Enabling NFS service: $(NFS_SERVICE)"
	@sudo systemctl enable --now $(NFS_SERVICE) 2>/dev/null || sudo systemctl enable --now nfs 2>/dev/null || true
	@sudo mkdir -p $(NFS_EXPORT_DIR)
	@sudo chmod 777 $(NFS_EXPORT_DIR)
	@echo "==> Configuring NFS exports..."
	@sudo grep -qxF '$(NFS_EXPORT_DIR) *(rw,sync,no_subtree_check,no_root_squash,insecure)' /etc/exports || \
		echo '$(NFS_EXPORT_DIR) *(rw,sync,no_subtree_check,no_root_squash,insecure)' | sudo tee -a /etc/exports
	@sudo exportfs -rav
	@echo "==> NFS export ready: $(NFS_EXPORT_DIR)"
	@echo "==> Server IP for NFS: $(SERVER_IP)"

# Install k3s server (control plane + worker)
server:
	@echo "==> Installing k3s server on $(SERVER_IP)..."
	@if ! command -v k3s >/dev/null 2>&1; then \
		curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server --disable=traefik --disable=servicelb --tls-san=$(SERVER_IP) --node-ip=$(SERVER_IP) --advertise-address=$(SERVER_IP)" sh -; \
	else \
		echo "k3s already installed"; \
	fi
	@echo "==> Waiting for k3s to be ready..."
	@sleep 5
	@until sudo kubectl get nodes 2>/dev/null | grep -q " Ready"; do sleep 2; done
	@echo "==> k3s server ready!"
	@echo "==> Node token for workers:"
	@sudo cat /var/lib/rancher/k3s/server/node-token

# Show worker join command
worker-join-cmd:
	@echo "==> Run this on worker nodes:"
	@echo "curl -sfL https://get.k3s.io | K3S_URL=https://$(SERVER_IP):6443 K3S_TOKEN=$$(sudo cat /var/lib/rancher/k3s/server/node-token) sh -"

# Join a worker node (run on worker VMs)
join-worker:
	@if [ -z "$(K3S_URL)" ] || [ -z "$(K3S_TOKEN)" ]; then \
		echo "Error: Set K3S_URL and K3S_TOKEN environment variables"; \
		echo "Example: make join-worker K3S_URL=https://192.168.1.100:6443 K3S_TOKEN=<token>"; \
		exit 1; \
	fi
	@echo "==> Joining k3s cluster..."
	@curl -sfL https://get.k3s.io | K3S_URL=$(K3S_URL) K3S_TOKEN=$(K3S_TOKEN) sh -
	@echo "==> Worker node joined!"

# Setup kubeconfig for local user
kubeconfig:
	@echo "==> Setting up kubeconfig..."
	@mkdir -p ~/.kube
	@sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
	@sudo chown $$(id -u):$$(id -g) ~/.kube/config
	@sed -i "s/127.0.0.1/$(SERVER_IP)/g" ~/.kube/config
	@echo "==> kubeconfig ready at ~/.kube/config"

# Install MetalLB
metallb:
	@echo "==> Installing MetalLB..."
	@kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.14.5/config/manifests/metallb-native.yaml
	@echo "==> Waiting for MetalLB controller..."
	@kubectl wait --namespace metallb-system \
		--for=condition=ready pod \
		--selector=component=controller \
		--timeout=120s 2>/dev/null || sleep 10
	@echo "==> Waiting for MetalLB webhook..."
	@sleep 5
	@for i in $$(seq 1 20); do \
		if kubectl get endpoints -n metallb-system webhook-service -o jsonpath='{.subsets[0].addresses[0].ip}' 2>/dev/null | grep -q .; then \
			echo "Webhook service ready!"; \
			break; \
		fi; \
		echo "Waiting for webhook... ($$i/20)"; \
		sleep 3; \
	done
	@echo "==> Configuring MetalLB IP pool..."
	@sed "s/HOST_IP_PLACEHOLDER/$(SERVER_IP)/g" metallb-config.yaml | kubectl apply -f -
	@echo "==> MetalLB configured with IP: $(SERVER_IP)"

# Install Traefik with LoadBalancer
traefik:
	@echo "==> Installing Traefik..."
	@helm repo add traefik https://traefik.github.io/charts 2>/dev/null || true
	@helm repo update
	@kubectl create namespace traefik --dry-run=client -o yaml | kubectl apply -f -
	@helm upgrade --install traefik traefik/traefik \
		--namespace traefik \
		--set service.type=LoadBalancer \
		--set ports.web.exposedPort=80 \
		--set ports.websecure.exposedPort=443 \
		--set ingressClass.enabled=true \
		--set ingressClass.isDefaultClass=true
	@echo "==> Waiting for Traefik..."
	@kubectl wait --namespace traefik \
		--for=condition=ready pod \
		--selector=app.kubernetes.io/name=traefik \
		--timeout=90s
	@echo "==> Traefik ready!"

# Install NFS provisioner
storage:
	@echo "==> Installing NFS subdir external provisioner..."
	@helm repo add nfs-subdir-external-provisioner \
		https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner 2>/dev/null || true
	@helm repo update
	@helm upgrade --install nfs-provisioner \
		nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
		--set nfs.server=$(SERVER_IP) \
		--set nfs.path=$(NFS_EXPORT_DIR) \
		--set storageClass.name=$(STORAGE_CLASS) \
		--set storageClass.allowVolumeExpansion=true
	@echo "==> Waiting for StorageClass..."
	@until kubectl get storageclass $(STORAGE_CLASS) >/dev/null 2>&1; do sleep 1; done
	@echo "==> Creating PVC..."
	@kubectl apply -f pvc.yaml
	@kubectl wait --for=jsonpath='{.status.phase}'=Bound pvc/pcap-core --timeout=120s
	@echo "==> Storage ready!"

# Show status
status:
	@echo ""
	@echo "=== Nodes ==="
	@kubectl get nodes
	@echo ""
	@echo "=== StorageClasses ==="
	@kubectl get storageclass
	@echo ""
	@echo "=== PVCs ==="
	@kubectl get pvc
	@echo ""
	@echo "=== Services (Traefik/MetalLB) ==="
	@kubectl get svc -n traefik 2>/dev/null || echo "Traefik not installed"
	@kubectl get svc -n metallb-system 2>/dev/null | grep -v webhook || echo "MetalLB not installed"

# Clean up everything
clean:
	@echo "==> Cleaning up k3s cluster..."
	@kubectl delete deployment -l chall-manager.ctfer.io/challenge --all-namespaces 2>/dev/null || true
	@kubectl delete pvc pcap-core 2>/dev/null || true
	@helm uninstall nfs-provisioner 2>/dev/null || true
	@helm uninstall traefik -n traefik 2>/dev/null || true
	@kubectl delete -f https://raw.githubusercontent.com/metallb/metallb/v0.14.5/config/manifests/metallb-native.yaml 2>/dev/null || true
	@echo "==> Uninstalling k3s..."
	@/usr/local/bin/k3s-uninstall.sh 2>/dev/null || true
	@echo "==> Cleaning up NFS..."
	@sudo sed -i "\|$(NFS_EXPORT_DIR)|d" /etc/exports
	@sudo exportfs -rav 2>/dev/null || true
	@sudo rm -rf $(NFS_EXPORT_DIR)
	@echo "==> Cleanup complete!"

# Help
help:
	@echo "K3s Chall-Manager Setup"
	@echo ""
	@echo "Targets:"
	@echo "  all          - Full setup: NFS, k3s server, MetalLB, storage"
	@echo "  nfs          - Install and configure NFS server"
	@echo "  server       - Install k3s control plane"
	@echo "  metallb      - Install MetalLB for LoadBalancer services"
	@echo "  storage      - Install NFS provisioner and create PVC"
	@echo "  kubeconfig   - Copy kubeconfig for current user"
	@echo "  worker-join-cmd - Show command to join worker nodes"
	@echo "  status       - Show cluster status"
	@echo "  clean        - Remove everything"
	@echo ""
	@echo "On worker nodes, run:"
	@echo '  curl -sfL https://get.k3s.io | K3S_URL=https://<SERVER_IP>:6443 K3S_TOKEN=<token> sh -'
