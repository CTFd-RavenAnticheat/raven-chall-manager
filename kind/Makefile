ifneq (,$(wildcard .env))
	include .env
	export
endif

CLUSTER_NAME := kind
KIND_CONFIG   := kind.yaml
PVC_FILE := pvc.yaml
POD_FILE := pod.yaml
NFS_SERVER = $(shell docker network inspect kind -f '{{range .IPAM.Config}}{{.Gateway}}{{end}}' 2>/dev/null | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}' | head -1)
STORAGE_CLASS := nfs-rwx
NFS_EXPORT_DIR := /srv/nfs/k8s
NFS_CIDR = $(shell docker network inspect kind -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}' | head -1)
NFS_EXPORT_LINE = $(NFS_EXPORT_DIR) $(NFS_CIDR)(rw,sync,no_subtree_check,no_root_squash)
TRAEFIK_NAMESPACE := networking
HOST_IP ?= $(shell ip route get 1 | awk '{print $$(NF-2); exit}')
OS_ID := $(shell . /etc/os-release 2>/dev/null && echo $$ID)
OS_LIKE := $(shell . /etc/os-release 2>/dev/null && echo $$ID_LIKE)
# Arch Linux
ifeq ($(OS_ID),arch)
	NFS_PKG := nfs-utils
	NFS_SERVICE := nfs-server
endif

# Ubuntu / Debian
ifeq ($(OS_ID),ubuntu)
	NFS_PKG := nfs-kernel-server
	NFS_SERVICE := nfs-kernel-server
endif

ifeq ($(OS_ID),debian)
	NFS_PKG := nfs-kernel-server
	NFS_SERVICE := nfs-kernel-server
endif

# Safety check
ifndef NFS_PKG
$(error Unsupported OS ($(OS_ID)). Supported: arch, ubuntu, debian)
endif
.PHONY: all nfs status app cluster clean nfs-host storage traefik metallb

all: nfs-host cluster nfs metallb traefik storage app status

nfs-host:
	@echo "==> Host OS detected: $(OS_ID)"
	@echo "==> Installing NFS package: $(NFS_PKG)"
	@command -v exportfs >/dev/null 2>&1 || { \
		echo "Installing $(NFS_PKG)"; \
		sudo sh -c ' \
			if command -v pacman >/dev/null; then \
				pacman -S --needed --noconfirm $(NFS_PKG); \
			elif command -v apt >/dev/null; then \
				apt update && apt install -y $(NFS_PKG); \
			else \
				echo "No supported package manager found"; exit 1; \
			fi'; \
	}
	@echo "==> Enabling NFS service: $(NFS_SERVICE)"
	@sudo systemctl enable --now $(NFS_SERVICE)
	@sudo mkdir -p $(NFS_EXPORT_DIR)
	@sudo chmod 777 $(NFS_EXPORT_DIR)
	@echo "==> Configuring NFS exports for all Docker networks..."
	@sudo grep -qxF '$(NFS_EXPORT_DIR) *(rw,sync,no_subtree_check,no_root_squash)' /etc/exports || \
		echo '$(NFS_EXPORT_DIR) *(rw,sync,no_subtree_check,no_root_squash)' | sudo tee -a /etc/exports
	@sudo exportfs -rav
	@echo "==> NFS export ready: $(NFS_EXPORT_DIR)"

cluster:
	-kind get clusters | grep -q $(CLUSTER_NAME) || \
	kind create cluster --name $(CLUSTER_NAME) --config $(KIND_CONFIG)
	@echo "==> Updating kubeconfig with Docker network IP for container access..."
	@DOCKER_IP=$$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' kind-control-plane); \
	kubectl config set-cluster kind-kind --server=https://$$DOCKER_IP:6443

nfs:
	@echo "==> Detecting kind network configuration..."
	@NFS_SERVER=$$(docker network inspect kind -f '{{range .IPAM.Config}}{{.Gateway}}{{end}}' 2>/dev/null | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}' | head -1); \
	if [ -z "$$NFS_SERVER" ]; then \
		echo "Error: kind cluster not found or network not configured"; \
		exit 1; \
	fi; \
	echo "==> Using NFS server: $$NFS_SERVER"; \
	helm repo add nfs-subdir-external-provisioner \
	  https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner || true; \
	helm repo update; \
	helm upgrade --install nfs-provisioner \
	  nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
	  --set nfs.server=$$NFS_SERVER \
	  --set nfs.path=$(NFS_EXPORT_DIR) \
	  --set storageClass.name=$(STORAGE_CLASS)

metallb:
	@echo "==> Installing MetalLB..."
	kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.14.3/config/manifests/metallb-native.yaml
	@echo "==> Waiting for MetalLB controller pod to be ready..."
	kubectl wait --namespace metallb-system --for=condition=ready pod --selector=component=controller --timeout=120s
	@echo "==> Waiting for MetalLB webhook service to be ready..."
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		if kubectl get endpoints -n metallb-system webhook-service -o jsonpath='{.subsets[0].addresses[0].ip}' 2>/dev/null | grep -q .; then \
			echo "Webhook service is ready!"; \
			break; \
		fi; \
		echo "Waiting for webhook endpoints... (attempt $$i/10)"; \
		sleep 3; \
	done
	@echo "==> Configuring MetalLB IP pool with IP: $(HOST_IP)..."
	@sed "s/HOST_IP_PLACEHOLDER/$(HOST_IP)/g" metallb-config.yaml | kubectl apply -f -
	@echo "==> MetalLB configured!"

traefik:
	@echo "==> Installing Traefik in namespace: $(TRAEFIK_NAMESPACE)"
	kubectl create namespace $(TRAEFIK_NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	helm repo add traefik https://traefik.github.io/charts || true
	helm repo update
	@echo "==> Configuring Traefik with LoadBalancer type (MetalLB)..."
	helm upgrade --install traefik traefik/traefik \
	  --namespace $(TRAEFIK_NAMESPACE) \
	  --set ingressClass.enabled=true \
	  --set ingressClass.isDefaultClass=true \
	  --set service.type=LoadBalancer \
	  --set ports.web.exposedPort=80 \
	  --set ports.websecure.exposedPort=443 \
	  --set providers.kubernetesIngress.publishedService.enabled=true
	@echo "==> Waiting for Traefik to be ready..."
	kubectl wait --namespace $(TRAEFIK_NAMESPACE) \
	  --for=condition=ready pod \
	  --selector=app.kubernetes.io/name=traefik \
	  --timeout=90s
	@echo "==> Traefik ingress controller ready!"

storage:
	@echo "==> Waiting for StorageClass to be available..."
	@until kubectl get storageclass $(STORAGE_CLASS) >/dev/null 2>&1; do sleep 1; done
	kubectl apply -f $(PVC_FILE)

app:
	@echo "==> Waiting for PVC to be bound..."
	@kubectl wait --for=jsonpath='{.status.phase}'=Bound pvc/pcap-core --timeout=60s
	kubectl apply -f $(POD_FILE)

status:
	@echo ""
	@echo "--- StorageClass ---"
	kubectl get storageclass
	@echo ""
	@echo "--- PVC ---"
	kubectl get pvc
	@echo ""
	@echo "--- Pod ---"
	kubectl get pod

clean:
	# Find pods starting with emp-dep across all namespaces and delete them
	-kubectl get pods -A --no-headers | grep "emp-dep-" | awk '{print $$2 " -n " $$1}' | xargs -L1 kubectl delete pod
	-kubectl delete -f $(POD_FILE) --ignore-not-found
	-kubectl delete -f $(PVC_FILE) --ignore-not-found
	-helm uninstall traefik --namespace $(TRAEFIK_NAMESPACE)
	-helm uninstall nfs-provisioner
	-kubectl delete -f https://raw.githubusercontent.com/metallb/metallb/v0.14.3/config/manifests/metallb-native.yaml --ignore-not-found
	kind delete cluster --name $(CLUSTER_NAME)
