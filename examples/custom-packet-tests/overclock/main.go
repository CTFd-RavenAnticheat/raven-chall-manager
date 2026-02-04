package main

import (
	"github.com/CTFd-RavenAnticheat/raven-chall-manager/sdk"
	k8s "github.com/CTFd-RavenAnticheat/raven-chall-manager/sdk/kubernetes"
	"github.com/pulumi/pulumi/sdk/v3/go/pulumi"
)

const (
	flag = "24HIUT{To0_W3ak_c#yp7o}"
)

// Example: Web challenge with packet capture enabled
// This will capture all HTTP traffic between users and the challenge
func main() {
	sdk.Run(func(req *sdk.Request, resp *sdk.Response, opts ...pulumi.ResourceOption) error {
		variated := pulumi.String(sdk.Variate(req.Config.Identity, flag,
			sdk.WithSpecial(true),
		))

		cm, err := k8s.NewExposedMonopod(req.Ctx, "test", &k8s.ExposedMonopodArgs{
			ChallengeID:      pulumi.String(req.Config.ChallengeID),
			PacketCapturePVC: pulumi.StringPtr("pcap-core"),
			Identity:         pulumi.String(req.Config.Identity),
			Hostname:         pulumi.String("172.17.0.1"),
			Container: k8s.ContainerArgs{
				Image: pulumi.String("registry.gitlab.com/bitravens1/darkesthour26/overclock"),
				Ports: k8s.PortBindingArray{
					k8s.PortBindingArgs{
						Port:       pulumi.Int(1000),
						ExposeType: k8s.ExposeNodePort,
					},
				},
				Files: pulumi.StringMap{
					"/app/flag.txt": variated,
				},
				// Enable packet capture to record all user interactions
				PacketCapture: pulumi.BoolPtr(true),

				// Optional: Resource limits for the main container
				LimitCPU:    pulumi.StringPtr("500m"),
				LimitMemory: pulumi.StringPtr("256Mi"),
			},
			IngressNamespace: pulumi.String("networking"),
			IngressLabels: pulumi.ToStringMap(map[string]string{
				"app": "traefik",
			}),
		}, opts...)
		if err != nil {
			return err
		}

		// The packet capture will be stored at:
		// /captures/<identity>-web-challenge.pcap
		// This path will also be available in the Instance.CaptureFiles field

		resp.ConnectionInfo = pulumi.Sprintf("nc %s",
			cm.URLs.MapIndex(pulumi.String("1000/TCP")))
		resp.Flag = variated.ToStringOutput()

		return nil
	})
}
