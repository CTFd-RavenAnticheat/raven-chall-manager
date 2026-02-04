ifneq (,$(wildcard .env))
	include .env
	export
endif

CLUSTER_NAME := kind
KIND_TEMPLATE := kind.yaml.tmpl
KIND_CONFIG   := kind.yaml
PVC_FILE := pvc.yaml
POD_FILE := pod.yaml
NFS_SERVER := 172.17.0.1
STORAGE_CLASS := nfs-rwx
NFS_EXPORT_DIR := /srv/nfs/k8s
NFS_CIDR := 172.17.0.0/16
NFS_EXPORT_LINE := $(NFS_EXPORT_DIR) $(NFS_CIDR)(rw,sync,no_subtree_check,no_root_squash)
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
.PHONY: all nfs status app kind-config cluster clean nfs-host storage

all: cluster nfs storage app status

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
	@sudo grep -qxF '$(NFS_EXPORT_LINE)' /etc/exports || \
		echo '$(NFS_EXPORT_LINE)' | sudo tee -a /etc/exports
	@sudo exportfs -rav
	@echo "==> NFS export ready: $(NFS_EXPORT_DIR)"

kind-config:
	@echo "Rendering kind config from env"
	envsubst < $(KIND_TEMPLATE) > $(KIND_CONFIG)

cluster: kind-config
	-kind get clusters | grep -q $(CLUSTER_NAME) || \
	kind create cluster --name $(CLUSTER_NAME) --config $(KIND_CONFIG)
	-rm -f $(KIND_CONFIG)

nfs:
	helm repo add nfs-subdir-external-provisioner \
	  https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner || true
	helm repo update
	helm upgrade --install nfs-provisioner \
	  nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
	  --set nfs.server=$(NFS_SERVER) \
	  --set nfs.path=$(NFS_EXPORT_DIR) \
	  --set storageClass.name=$(STORAGE_CLASS)

storage:
	kubectl apply -f $(PVC_FILE)

app:
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
	-kubectl delete -f $(POD_FILE)
	-kubectl get pod --no-headers | awk '/^emp-dep-/{print $$1}' | xargs -r kubectl delete pod
	-kubectl delete -f $(PVC_FILE)
	-helm uninstall nfs-provisioner
	-kind delete cluster --name $(CLUSTER_NAME)
