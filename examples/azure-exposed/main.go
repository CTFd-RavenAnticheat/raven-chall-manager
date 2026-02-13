package main

import (
	"github.com/ctfer-io/chall-manager/sdk"
	k8s "github.com/ctfer-io/chall-manager/sdk/kubernetes"
	"github.com/pulumi/pulumi/sdk/v3/go/pulumi"
)

const (
	// Your Azure VM's public IP
	publicIP = "102.31.141.138"
	flag     = "FLAG{example_flag}"
)

func main() {
	sdk.Run(func(req *sdk.Request, resp *sdk.Response, opts ...pulumi.ResourceOption) error {
		variated := pulumi.String(sdk.Variate(req.Config.Identity, flag,
			sdk.WithSpecial(true),
		))

		cm, err := k8s.NewExposedMonopod(req.Ctx, "azure-challenge", &k8s.ExposedMonopodArgs{
			Identity: pulumi.String(req.Config.Identity),
			// Use nip.io for wildcard DNS pointing to your Azure public IP
			Hostname: pulumi.String(publicIP + ".nip.io"),
			Container: k8s.ContainerArgs{
				Image: pulumi.String("nginx:latest"),
				Ports: k8s.PortBindingArray{
					k8s.PortBindingArgs{
						Port:       pulumi.Int(80),
						ExposeType: k8s.ExposeIngress, // Use Ingress with Traefik
					},
				},
				Files: pulumi.StringMap{
					"/usr/share/nginx/html/flag.txt": variated,
				},
			},
			// Traefik ingress configuration
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

		resp.ConnectionInfo = pulumi.Sprintf("curl -v http://%s", cm.URLs.MapIndex(pulumi.String("80/TCP")))
		resp.Flag = variated.ToStringOutput()
		return nil
	})
}
