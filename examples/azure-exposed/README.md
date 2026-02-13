# Azure Cloud Ingress with Chall-Manager

This example shows how to expose chall-manager challenges using Azure VM's public IP with Traefik ingress controller.

## Architecture

```
Internet → Azure Public IP (102.31.141.138)
    ↓
Azure VM with Kind Cluster
    ↓
Traefik Ingress Controller (NodePort 30080/30443)
    ↓
Challenge Pods
```

## Prerequisites

1. **Azure VM** with public IP running kind cluster
2. **Traefik** ingress controller installed (already configured in your setup)
3. **Azure NSG** rules allowing ports 80 and 443

## Step 1: Configure Azure Network Security Group

Open ports 80 and 443 on your Azure VM's NSG:

```bash
# Find your resource group and VM name
az vm list --query "[].{Name:name, ResourceGroup:resourceGroup}" -o table

# Set variables (replace with your values)
RG_NAME="your-resource-group"
VM_NAME="archlinux"

# Get NSG name
NSG_NAME=$(az vm show -n $VM_NAME -g $RG_NAME --query "networkProfile.networkInterfaces[0].id" -o tsv | \
  xargs az network nic show --ids | \
  jq -r '.networkSecurityGroup.id' | \
  xargs basename)

# Create inbound rules for HTTP and HTTPS
az network nsg rule create \
  --resource-group $RG_NAME \
  --nsg-name $NSG_NAME \
  --name AllowHTTP \
  --protocol tcp \
  --priority 100 \
  --destination-port-range 80 \
  --access allow \
  --direction inbound \
  --description "Allow HTTP traffic for challenges"

az network nsg rule create \
  --resource-group $RG_NAME \
  --nsg-name $NSG_NAME \
  --name AllowHTTPS \
  --protocol tcp \
  --priority 101 \
  --destination-port-range 443 \
  --access allow \
  --direction inbound \
  --description "Allow HTTPS traffic for challenges"
```

## Step 2: Verify Kind Port Mappings

Your kind cluster should have these port mappings (already configured):

```bash
docker port kind-control-plane
# 30080/tcp -> 0.0.0.0:80
# 30443/tcp -> 0.0.0.0:443
```

## Step 3: Configure Challenge Hostname

Update your challenge scenario to use your public IP with nip.io:

```go
package main

import (
	"github.com/ctfer-io/chall-manager/sdk"
	k8s "github.com/ctfer-io/chall-manager/sdk/kubernetes"
	"github.com/pulumi/pulumi/sdk/v3/go/pulumi"
)

func main() {
	sdk.Run(func(req *sdk.Request, resp *sdk.Response, opts ...pulumi.ResourceOption) error {
		cm, err := k8s.NewExposedMonopod(req.Ctx, "my-challenge", &k8s.ExposedMonopodArgs{
			Identity: pulumi.String(req.Config.Identity),
			
			// Option 1: Use nip.io (wildcard DNS)
			Hostname: pulumi.String("102.31.141.138.nip.io"),
			
			// Option 2: Use your own domain pointing to 102.31.141.138
			// Hostname: pulumi.String("challenges.yourdomain.com"),
			
			Container: k8s.ContainerArgs{
				Image: pulumi.String("nginx:latest"),
				Ports: k8s.PortBindingArray{
					k8s.PortBindingArgs{
						Port:       pulumi.Int(80),
						ExposeType: k8s.ExposeIngress, // Use ingress
					},
				},
			},
			
			// Traefik-specific configuration
			IngressAnnotations: pulumi.ToStringMap(map[string]string{
				"traefik.ingress.kubernetes.io/router.entrypoints": "web, websecure",
			}),
			IngressNamespace: pulumi.String("networking"),
			IngressLabels: pulumi.ToStringMap(map[string]string{
				"app": "traefik",
			}),
		}, opts...)
		
		if err != nil {
			return err
		}
		
		resp.ConnectionInfo = pulumi.Sprintf("curl http://%s", 
			cm.URLs.MapIndex(pulumi.String("80/TCP")))
		return nil
	})
}
```

## Step 4: Build and Push Scenario

```bash
# Build the scenario
go build -o scenario main.go

# Package it
tar czf scenario.tar.gz scenario

# Push to OCI registry (if using one)
# Or use it directly with chall-manager
```

## Step 5: Create Challenge in Chall-Manager

```bash
# Using chall-manager-cli
chall-manager-cli --url localhost:8080 challenge create \
  --id azure-challenge \
  --scenario registry:5000/scenarios/azure-challenge:v1 \
  --dir examples/azure-exposed

# Create instance
chall-manager-cli --url localhost:8080 instance create \
  --challenge_id azure-challenge \
  --source_id test-user
```

## Step 6: Access Your Challenge

Once deployed, your challenge will be accessible at:

```bash
# With nip.io
curl http://102.31.141.138.nip.io

# With custom domain (if configured)
curl http://challenges.yourdomain.com
```

Each instance gets a unique subdomain based on the identity:
```
http://<instance-identity>.102.31.141.138.nip.io
```

## Troubleshooting

### 1. Connection Refused

Check if Traefik is running:
```bash
kubectl get pods -n networking
kubectl logs -n networking deployment/traefik
```

### 2. 404 Not Found

Check ingress configuration:
```bash
kubectl get ingress -A
kubectl describe ingress <ingress-name>
```

### 3. Timeout / Unreachable

Verify Azure NSG rules:
```bash
az network nsg rule list --nsg-name $NSG_NAME -g $RG_NAME --query "[?destinationPortRange=='80' || destinationPortRange=='443']" -o table
```

Test locally first:
```bash
curl -v http://localhost
```

### 4. Certificate Issues (HTTPS)

For HTTPS with Let's Encrypt, configure cert-manager:
```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml
```

Add annotation to ingress:
```go
IngressAnnotations: pulumi.ToStringMap(map[string]string{
	"cert-manager.io/cluster-issuer": "letsencrypt-prod",
}),
```

## Alternative: Using NodePort Directly

If you don't want to use ingress, you can expose directly via NodePort:

```go
Ports: k8s.PortBindingArray{
	k8s.PortBindingArgs{
		Port:       pulumi.Int(8080),
		ExposeType: k8s.ExposeNodePort, // Instead of ExposeIngress
		NodePort:   pulumi.Int(30080),  // Optional: specify NodePort
	},
},
```

Then access via: `http://102.31.141.138:30080`

## Using Custom Domain

If you have a domain, configure DNS:

```
A Record: *.challenges.yourdomain.com → 102.31.141.138
```

Then update hostname:
```go
Hostname: pulumi.String("challenges.yourdomain.com"),
```

## References

- [nip.io](https://nip.io) - Wildcard DNS for any IP
- [Traefik Documentation](https://doc.traefik.io/traefik/providers/kubernetes-ingress/)
- [Kind Ingress](https://kind.sigs.k8s.io/docs/user/ingress/)
