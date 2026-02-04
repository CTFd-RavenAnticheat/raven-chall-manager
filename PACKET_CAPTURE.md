# Packet Capture Feature

## Overview

The chall-manager now supports automated packet capture for CTF challenge instances. When enabled, this feature captures all TCP/UDP traffic between users and challenge containers, including:

- Full packet payloads
- Packet lengths
- Timing information (timestamps for each packet)
- Delay between server responses and next user requests

**Note:** Source IP addresses and ports are captured in the pcap file but can be filtered out during analysis if needed.

## How It Works

When packet capture is enabled for a container:

1. A **sidecar container** running `tcpdump` is automatically deployed alongside your challenge container
2. The sidecar captures all network traffic on the configured ports
3. Capture data is stored in a **Persistent Volume** (1GB by default)
4. Each packet is timestamped with ISO 8601 format for timing analysis
5. The capture file location is tracked in the instance metadata

## Architecture

```
Pod:
├── Main Container (your challenge)
├── Packet Capture Sidecar
│   ├── Image: nicolaka/netshoot:v0.13
│   ├── Tool: tcpdump
│   └── Capabilities: NET_RAW, NET_ADMIN
└── Shared Volume: /captures
```

## Usage

### Enable Packet Capture

Add `PacketCapture: pulumi.BoolPtr(true)` to your container configuration:

```go
package main

import (
	"github.com/ctfer-io/chall-manager/sdk"
	"github.com/ctfer-io/chall-manager/sdk/kubernetes"
	"github.com/pulumi/pulumi/sdk/v3/go/pulumi"
)

func main() {
	sdk.Run(func(req *sdk.Request, resp *sdk.Response, opts ...pulumi.ResourceOption) error {
		cm, err := kubernetes.NewExposedMonopod(req.Ctx, "example", &kubernetes.ExposedMonopodArgs{
			Identity: pulumi.String(req.Config.Identity),
			Hostname: pulumi.String("ctf.example.com"),
			Container: kubernetes.ContainerArgs{
				Image: pulumi.String("your-challenge:latest"),
				Ports: kubernetes.PortBindingArray{
					kubernetes.PortBindingArgs{
						Port:       pulumi.Int(8080),
						ExposeType: kubernetes.ExposeIngress,
					},
				},
				PacketCapture: pulumi.BoolPtr(true), // Enable packet capture
			},
			IngressNamespace: pulumi.String("networking"),
			IngressLabels: pulumi.ToStringMap(map[string]string{
				"app": "traefik",
			}),
		}, opts...)
		if err != nil {
			return err
		}

		resp.ConnectionInfo = pulumi.Sprintf("https://%s", cm.URLs.MapIndex(pulumi.String("8080/TCP")))
		return nil
	})
}
```

### Capture File Naming

Capture files are named based on the instance identity and container name:

- Format: `/captures/<label>-<identity>-<container>.pcap` (with label)
- Format: `/captures/<identity>-<container>.pcap` (without label)

### Accessing Capture Files

The capture file path is stored in the `Instance` struct under the `CaptureFiles` field:

```go
type Instance struct {
	Identity       string            `json:"identity"`
	ChallengeID    string            `json:"challenge_id"`
	// ... other fields ...
	CaptureFiles   map[string]string `json:"capture_files,omitempty"` // Maps container name to capture file path
}
```

## Analyzing Captured Traffic

### Using tcpdump

```bash
# Read the capture file
tcpdump -r /captures/instance-xyz.pcap

# Filter specific protocols
tcpdump -r /captures/instance-xyz.pcap 'tcp port 8080'

# Show packet lengths and timing
tcpdump -r /captures/instance-xyz.pcap -tttt -vv

# Extract HTTP requests
tcpdump -r /captures/instance-xyz.pcap -A 'tcp port 8080'
```

### Using tshark (Wireshark CLI)

```bash
# Convert to JSON with timing info
tshark -r /captures/instance-xyz.pcap -T json > traffic.json

# Extract packet lengths and inter-packet delays
tshark -r /captures/instance-xyz.pcap -T fields \
  -e frame.number \
  -e frame.time_relative \
  -e frame.len \
  -e ip.src \
  -e ip.dst \
  -E header=y \
  -E separator=,
```

### Using Python (scapy)

```python
from scapy.all import rdpcap, TCP, UDP
import datetime

packets = rdpcap('/captures/instance-xyz.pcap')

for i, pkt in enumerate(packets):
    if TCP in pkt or UDP in pkt:
        print(f"Packet {i}:")
        print(f"  Time: {datetime.datetime.fromtimestamp(float(pkt.time))}")
        print(f"  Length: {len(pkt)} bytes")
        if i > 0:
            delay = float(pkt.time) - float(packets[i-1].time)
            print(f"  Delay from previous: {delay:.6f}s")
```

## Resource Requirements

The packet capture sidecar uses minimal resources:

- **CPU Limit**: 100m (0.1 core)
- **Memory Limit**: 128Mi
- **CPU Request**: 50m
- **Memory Request**: 64Mi
- **Storage**: 1Gi PersistentVolume (configurable)

## Security Considerations

1. **Capabilities**: The sidecar requires `NET_RAW` and `NET_ADMIN` capabilities to capture packets
2. **Access Control**: Ensure proper RBAC policies are in place to restrict access to capture files
3. **Storage**: Capture files may contain sensitive user data - implement retention policies
4. **Privacy**: Consider regulatory requirements (GDPR, etc.) before enabling packet capture

## Troubleshooting

### Sidecar not starting

Check pod events:
```bash
kubectl describe pod <pod-name>
```

Verify security context allows NET_RAW capability:
```bash
kubectl get pod <pod-name> -o yaml | grep -A 5 securityContext
```

### No packets captured

1. Verify traffic is reaching the container
2. Check sidecar logs: `kubectl logs <pod-name> -c <identity>-pcap`
3. Ensure the port filter matches your exposed ports

### Storage full

Increase PVC size in the deployment configuration or implement automatic rotation.

## Future Enhancements

Potential improvements:

- [ ] Configurable capture filters (exclude certain traffic patterns)
- [ ] Automatic capture file rotation based on size/time
- [ ] Real-time streaming to external analysis tools
- [ ] Integration with OpenTelemetry for network observability metrics
- [ ] Post-processing to extract timing statistics automatically
