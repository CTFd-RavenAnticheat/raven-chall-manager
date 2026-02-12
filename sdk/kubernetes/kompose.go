package kubernetes

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log"
	"maps"
	"os"
	"path/filepath"
	"reflect"
	"slices"
	"strings"
	"sync"

	"github.com/kubernetes/kompose/pkg/app"
	"github.com/kubernetes/kompose/pkg/kobject"
	corev1 "github.com/pulumi/pulumi-kubernetes/sdk/v4/go/kubernetes/core/v1"
	metav1 "github.com/pulumi/pulumi-kubernetes/sdk/v4/go/kubernetes/meta/v1"
	netwv1 "github.com/pulumi/pulumi-kubernetes/sdk/v4/go/kubernetes/networking/v1"
	yamlv2 "github.com/pulumi/pulumi-kubernetes/sdk/v4/go/kubernetes/yaml/v2"
	"github.com/pulumi/pulumi/sdk/v3/go/pulumi"
	"go.uber.org/multierr"
	cv1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/runtime"
)

var (
	kdir = filepath.Join(os.TempDir(), "chall-manager", "kompose")
)

func init() {
	_ = os.MkdirAll(kdir, os.ModePerm)
}

type Kompose struct {
	pulumi.ResourceState

	ns          *corev1.Namespace
	innspol     *netwv1.NetworkPolicy
	dnspol      *netwv1.NetworkPolicy
	internspol  *netwv1.NetworkPolicy
	internetpol *netwv1.NetworkPolicy

	cg       *yamlv2.ConfigGroup
	svcs     ServiceMapMapOutput
	svcSpecs ServiceSpecMapMapOutput
	ings     IngressMapMapOutput
	ingSpecs IngressSpecMapMapOutput
	ntps     []*netwv1.NetworkPolicy

	URLs pulumi.StringMapMapOutput
}

// NewKompose deploys a docker compose manifest on Kubernetes, using Kompose.
// It creates a namespace per instance, and isolate it from the others.
//
// WARNING: does not support [env_file].
func NewKompose(ctx *pulumi.Context, name string, args *KomposeArgs, opts ...pulumi.ResourceOption) (*Kompose, error) {
	kmp := &Kompose{
		URLs: pulumi.StringMapMap{}.ToStringMapMapOutput(),
		// Must init map else nil-pointer dereference
		svcs:     ServiceMapMap{}.ToServiceMapMapOutput(),
		svcSpecs: ServiceSpecMapMap{}.ToServiceSpecMapMapOutput(),
		ings:     IngressMapMap{}.ToIngressMapMapOutput(),
		ingSpecs: IngressSpecMapMap{}.ToIngressSpecMapMapOutput(),
	}

	if args == nil {
		return nil, errors.New("nil args")
	}
	in := args.ToKomposeArgsOutput()
	if err := kmp.check(in); err != nil {
		return nil, err
	}

	if err := ctx.RegisterComponentResource("ctfer-io:chall-manager/sdk:kubernetes.Kompose", name, kmp, opts...); err != nil {
		return nil, err
	}
	opts = append(opts, pulumi.Parent(kmp))

	if err := kmp.provision(ctx, in, opts...); err != nil {
		return nil, err
	}
	if err := kmp.outputs(ctx, in); err != nil {
		return nil, err
	}

	return kmp, nil
}

func (kmp *Kompose) check(in KomposeArgsOutput) (merr error) {
	wg := sync.WaitGroup{}
	checks := 5 // number of checks
	wg.Add(checks)
	cerr := make(chan error, checks)

	in.Identity().ApplyT(func(id string) (err error) {
		defer wg.Done()

		if id == "" {
			err = errors.New("identity could not be empty")
		}
		cerr <- err
		return
	})
	in.Hostname().ApplyT(func(hostname string) (err error) {
		defer wg.Done()

		if hostname == "" {
			err = errors.New("hostname could not be empty")
		}
		cerr <- err
		return
	})
	// Check the YAML manifest can be converted through Kompose
	in.ApplyT(func(in KomposeArgsRaw) error {
		defer wg.Done()

		// Don't allow an empty YAML file, as kompose allows it
		// yet does not produce anything...
		// We expect that if an empty compose file, the ChallMaker/Ops
		// did not want that (they don't try to deploy edge cases).
		if in.YAML == "" {
			cerr <- errors.New("empty YAML is not allowed")
			return nil
		}

		// Ensure docker compose can be transformd to YAML manifest
		_, objs, err := kompose(in.YAML)
		if err != nil {
			cerr <- err
			return nil
		}

		// What are the services, and on what do they listen ?
		svcs := map[string]map[string]struct{}{}
		for _, obj := range objs {
			if svc, ok := obj.(*cv1.Service); ok {
				svcs[svc.Name] = map[string]struct{}{}
				for _, p := range svc.Spec.Ports {
					prot := p.Protocol
					if prot == "" {
						prot = cv1.ProtocolTCP
					}
					svcs[svc.Name][fmt.Sprintf("%d/%s", p.Port, prot)] = struct{}{}
				}
			}
		}

		// Check ports correspond
		var merr error
		for svcName, pbs := range in.Ports {
			svc, ok := svcs[svcName]
			if !ok {
				merr = multierr.Append(merr, fmt.Errorf("service %s not found", svcName))
				continue
			}
			for _, pb := range pbs {
				prot := pb.Protocol
				if prot == "" {
					prot = "TCP"
				}
				pbk := fmt.Sprintf("%d/%s", pb.Port, prot)

				if _, ok = svc[pbk]; !ok {
					merr = multierr.Append(merr, fmt.Errorf("service %s has no port binding for %s", svcName, pbk))
				}
			}
		}
		cerr <- merr
		return nil
	})
	// Ensure there is at least one port exposed
	in.Ports().ApplyT(func(pbm map[string][]PortBinding) error {
		defer wg.Done()

		if len(pbm) == 0 {
			cerr <- errors.New("no port bindings defined")
			return nil
		}
		return nil
	})
	// Ensure there is no rule duplication
	in.Ports().ApplyT(func(pbm map[string][]PortBinding) (merr error) {
		defer wg.Done()

		for name, pbs := range pbm {
			ps := map[string]struct{}{}
			dups := []string{}
			for _, p := range pbs {
				prot := p.Protocol
				if prot == "" {
					prot = "TCP"
				}
				k := fmt.Sprintf("expose %s on %d/%s", p.ExposeType, p.Port, prot)
				if _, ok := ps[k]; ok {
					dups = append(dups, k)
				}
				ps[k] = struct{}{}
			}
			if len(dups) != 0 {
				merr = multierr.Append(merr, fmt.Errorf("container %s has duplicated ports: %s", name, strings.Join(dups, ", ")))
			}
		}
		cerr <- merr
		return nil
	})

	wg.Wait()
	close(cerr)

	for err := range cerr {
		merr = multierr.Append(merr, err)
	}
	return merr
}

func (kmp *Kompose) provision(ctx *pulumi.Context, in KomposeArgsOutput, opts ...pulumi.ResourceOption) (err error) {
	// TODO @pandatix: analyze for a reuse of deploy/services/parts.Namespace, or at least share common ground -> reduce maintenance cost, keep security measures coherent
	// Create namespace
	kmp.ns, err = corev1.NewNamespace(ctx, "ns", &corev1.NamespaceArgs{
		Metadata: metav1.ObjectMetaArgs{
			Name: in.Identity(),
			Labels: pulumi.StringMap{
				// From https://raw.githubusercontent.com/kubernetes/website/main/content/en/examples/security/podsecurity-baseline.yaml
				"pod-security.kubernetes.io/enforce":         pulumi.String("baseline"),
				"pod-security.kubernetes.io/enforce-version": pulumi.String("latest"),
				"pod-security.kubernetes.io/warn":            pulumi.String("baseline"),
				"pod-security.kubernetes.io/warn-version":    pulumi.String("latest"),
			},
		},
	}, opts...)
	if err != nil {
		return
	}

	// => NetworkPolicy to grant all network interactions within the namespace
	kmp.innspol, err = netwv1.NewNetworkPolicy(ctx, "allow-all-within-namespace", &netwv1.NetworkPolicyArgs{
		Metadata: metav1.ObjectMetaArgs{
			Namespace: kmp.ns.Metadata.Name().Elem(),
		},
		Spec: netwv1.NetworkPolicySpecArgs{
			PodSelector: metav1.LabelSelectorArgs{}, // Selects all Pods in the namespace
			Ingress: netwv1.NetworkPolicyIngressRuleArray{
				netwv1.NetworkPolicyIngressRuleArgs{
					From: netwv1.NetworkPolicyPeerArray{
						netwv1.NetworkPolicyPeerArgs{
							PodSelector: metav1.LabelSelectorArgs{}, // Allows ingress from any Pod in the same namespace
						},
					},
				},
			},
			Egress: netwv1.NetworkPolicyEgressRuleArray{
				netwv1.NetworkPolicyEgressRuleArgs{
					To: netwv1.NetworkPolicyPeerArray{
						netwv1.NetworkPolicyPeerArgs{
							PodSelector: metav1.LabelSelectorArgs{}, // Allows egress to any Pod in the same namespace
						},
					},
				},
			},
			PolicyTypes: pulumi.ToStringArray([]string{
				"Ingress",
				"Egress",
			}),
		},
	}, opts...)
	if err != nil {
		return
	}

	// => NetworkPolicy to grant DNS resolution (complex scenarios could require
	// to reach other pods in the namespace, e.g. not a scenario that fits into
	// the sdk.ctfer.io/ExposedMonopod architecture, which then would use headless
	// services so DNS resolution).
	kmp.dnspol, err = netwv1.NewNetworkPolicy(ctx, "allow-kube-dns", &netwv1.NetworkPolicyArgs{
		Metadata: metav1.ObjectMetaArgs{
			Namespace: kmp.ns.Metadata.Name(),
			Labels: pulumi.StringMap{
				"app.kubernetes.io/component": pulumi.String("chall-manager"),
				"app.kubernetes.io/part-of":   pulumi.String("chall-manager"),
			},
		},
		Spec: netwv1.NetworkPolicySpecArgs{
			PolicyTypes: pulumi.ToStringArray([]string{
				"Egress",
			}),
			PodSelector: metav1.LabelSelectorArgs{},
			Egress: netwv1.NetworkPolicyEgressRuleArray{
				netwv1.NetworkPolicyEgressRuleArgs{
					To: netwv1.NetworkPolicyPeerArray{
						netwv1.NetworkPolicyPeerArgs{
							NamespaceSelector: metav1.LabelSelectorArgs{
								MatchLabels: pulumi.StringMap{
									"kubernetes.io/metadata.name": pulumi.String("kube-system"),
								},
							},
							PodSelector: metav1.LabelSelectorArgs{
								MatchLabels: pulumi.StringMap{
									"k8s-app": pulumi.String("kube-dns"),
								},
							},
						},
					},
					Ports: netwv1.NetworkPolicyPortArray{
						netwv1.NetworkPolicyPortArgs{
							Port:     pulumi.Int(53),
							Protocol: pulumi.String("UDP"),
						},
						netwv1.NetworkPolicyPortArgs{
							Port:     pulumi.Int(53),
							Protocol: pulumi.String("TCP"),
						},
					},
				},
			},
		},
	}, opts...)
	if err != nil {
		return
	}

	// => NetworkPolicy to deny all scenarios from reaching adjacent namespaces
	kmp.internspol, err = netwv1.NewNetworkPolicy(ctx, "deny-inter-ns", &netwv1.NetworkPolicyArgs{
		Metadata: metav1.ObjectMetaArgs{
			Namespace: kmp.ns.Metadata.Name(),
			Labels: pulumi.StringMap{
				"app.kubernetes.io/component": pulumi.String("chall-manager"),
				"app.kubernetes.io/part-of":   pulumi.String("chall-manager"),
			},
		},
		Spec: netwv1.NetworkPolicySpecArgs{
			PodSelector: metav1.LabelSelectorArgs{},
			PolicyTypes: pulumi.ToStringArray([]string{
				"Egress",
			}),
			Egress: netwv1.NetworkPolicyEgressRuleArray{
				netwv1.NetworkPolicyEgressRuleArgs{
					To: netwv1.NetworkPolicyPeerArray{
						netwv1.NetworkPolicyPeerArgs{
							NamespaceSelector: metav1.LabelSelectorArgs{
								MatchExpressions: metav1.LabelSelectorRequirementArray{
									metav1.LabelSelectorRequirementArgs{
										Key:      pulumi.String("kubernetes.io/metadata.name"),
										Operator: pulumi.String("NotIn"),
										Values: pulumi.StringArray{
											kmp.ns.Metadata.Name().Elem(),
										},
									},
								},
							},
						},
					},
				},
			},
		},
	}, opts...)
	if err != nil {
		return
	}

	// => NetworkPolicy to grant access to Internet IPs (required to download fonts, images, etc.)
	kmp.internetpol, err = netwv1.NewNetworkPolicy(ctx, "allow-internet", &netwv1.NetworkPolicyArgs{
		Metadata: metav1.ObjectMetaArgs{
			Namespace: kmp.ns.Metadata.Name(),
			Labels: pulumi.StringMap{
				"app.kubernetes.io/component": pulumi.String("chall-manager"),
				"app.kubernetes.io/part-of":   pulumi.String("chall-manager"),
			},
		},
		Spec: netwv1.NetworkPolicySpecArgs{
			PodSelector: metav1.LabelSelectorArgs{},
			PolicyTypes: pulumi.ToStringArray([]string{
				"Egress",
			}),
			Egress: netwv1.NetworkPolicyEgressRuleArray{
				netwv1.NetworkPolicyEgressRuleArgs{
					To: netwv1.NetworkPolicyPeerArray{
						netwv1.NetworkPolicyPeerArgs{
							IpBlock: netwv1.IPBlockArgs{
								Cidr: pulumi.String("0.0.0.0/0"),
								Except: pulumi.ToStringArray([]string{
									"10.0.0.0/8",     // internal Kubernetes cluster IP range
									"172.16.0.0/12",  // common internal IP range
									"192.168.0.0/16", // common internal IP range
								}),
							},
						},
					},
				},
			},
		},
	}, opts...)
	if err != nil {
		return
	}

	// => ConfigMap for packet capture daemon script (if packet capture enabled for any container)
	in.PacketCapture().ApplyT(func(pc map[string]interface{}) error {
		if len(pc) == 0 {
			return nil
		}
		// Check if any container has packet capture enabled
		hasPacketCapture := false
		for _, v := range pc {
			if enabled, ok := v.(bool); ok && enabled {
				hasPacketCapture = true
				break
			}
		}
		if !hasPacketCapture {
			return nil
		}

		pcapScriptName := pulumi.All(in.Identity(), in.Label()).ApplyT(func(all []any) string {
			id := all[0].(string)
			if lbl, ok := all[1].(string); ok && lbl != "" {
				return fmt.Sprintf("kmp-pcap-script-%s-%s", lbl, id)
			}
			return fmt.Sprintf("kmp-pcap-script-%s", id)
		}).(pulumi.StringOutput)

		labels := pulumi.All(in.Identity(), in.Label()).ApplyT(func(all []any) pulumi.StringMap {
			id := all[0].(string)
			if lbl, ok := all[1].(string); ok && lbl != "" {
				return pulumi.StringMap{
					"app.kubernetes.io/name":          pulumi.String(id),
					"app.kubernetes.io/component":     pulumi.String("chall-manager"),
					"app.kubernetes.io/part-of":       pulumi.String("chall-manager"),
					"chall-manager.ctfer.io/identity": pulumi.String(id),
					"chall-manager.ctfer.io/label":    pulumi.String(lbl),
				}
			}
			return pulumi.StringMap{
				"app.kubernetes.io/name":          pulumi.String(id),
				"app.kubernetes.io/component":     pulumi.String("chall-manager"),
				"app.kubernetes.io/part-of":       pulumi.String("chall-manager"),
				"chall-manager.ctfer.io/identity": pulumi.String(id),
			}
		}).(pulumi.StringMapOutput)

		_, err := corev1.NewConfigMap(ctx, "kmp-pcap-script", &corev1.ConfigMapArgs{
			Immutable: pulumi.BoolPtr(true),
			Metadata: metav1.ObjectMetaArgs{
				Name:      pcapScriptName,
				Namespace: kmp.ns.Metadata.Name().Elem(),
				Labels:    labels,
			},
			Data: pulumi.StringMap{
				"capture-daemon.sh": pulumi.String(captureDaemonScript),
			},
		}, opts...)
		if err != nil {
			return err
		}
		return nil
	})

	// Transform resources to match expected configuration
	opts = append(opts, pulumi.Transforms([]pulumi.ResourceTransform{
		// Inject namespace
		func(_ context.Context, args *pulumi.ResourceTransformArgs) *pulumi.ResourceTransformResult {
			switch args.Type {
			// Inject namespace on the fly
			case "kubernetes:apps/v1:Deployment", "kubernetes:core/v1:Service":
				args.Props["metadata"].(pulumi.Map)["namespace"] = in.Identity()
				return &pulumi.ResourceTransformResult{
					Props: args.Props,
					Opts:  args.Opts,
				}

			default:
				return nil
			}
		},
		// Make service NodePorts whenever required
		func(_ context.Context, args *pulumi.ResourceTransformArgs) *pulumi.ResourceTransformResult {
			if args.Type == "kubernetes:core/v1:Service" {
				svcName := strings.TrimPrefix(args.Name, "kompose:default/")
				svcType := ExposeInternal // valid default value
				wg := sync.WaitGroup{}
				wg.Add(1)
				in.Ports().MapIndex(pulumi.String(svcName)).ApplyT(func(pbs []PortBinding) error {
					for _, pb := range pbs {
						// This checks is valid as per the default K8s Service LoadBalancer behavior, i.e.
						// create a NodePort for a LoadBalancer, but can be further configured.
						// We don't support this for now, and keep the default+legacy behavior to support
						// older versions of Kubernetes.
						//
						// References:
						// - https://kubernetes.io/docs/concepts/services-networking/service/#loadbalancer
						// - https://kubernetes.io/docs/concepts/services-networking/service/#load-balancer-nodeport-allocation
						if slices.Contains([]ExposeType{
							ExposeNodePort,
							ExposeLoadBalancer,
						}, pb.ExposeType) {
							svcType = pb.ExposeType
						}
					}
					wg.Done()
					return nil
				})
				wg.Wait()

				switch svcType {
				case ExposeNodePort:
					args.Props["spec"].(pulumi.Map)["type"] = pulumi.String("NodePort")
					args.Props["metadata"].(pulumi.Map)["annotations"] = in.Ports().MapIndex(pulumi.String(svcName)).ApplyT(func(pbs []PortBinding) map[string]string {
						out := map[string]string{}
						for _, pb := range pbs {
							maps.Copy(out, pb.Annotations)
						}
						return out
					}).(pulumi.StringMapOutput)

				case ExposeLoadBalancer:
					args.Props["spec"].(pulumi.Map)["type"] = pulumi.String("LoadBalancer")
					args.Props["metadata"].(pulumi.Map)["annotations"] = in.Ports().MapIndex(pulumi.String(svcName)).ApplyT(func(pbs []PortBinding) map[string]string {
						out := map[string]string{}
						for _, pb := range pbs {
							maps.Copy(out, pb.Annotations)
						}
						return out
					}).(pulumi.StringMapOutput)

				default: // Internal (default value fall back here), or Ingress
					args.Props["spec"].(pulumi.Map)["type"] = pulumi.String("")
				}

				return &pulumi.ResourceTransformResult{
					Props: args.Props,
					Opts:  args.Opts,
				}
			}
			return nil
		},
		// Disable ServiceAccount auto-mount
		func(_ context.Context, args *pulumi.ResourceTransformArgs) *pulumi.ResourceTransformResult {
			if args.Type == "kubernetes:apps/v1:Deployment" {
				args.Props["spec"].(pulumi.Map)["template"].(pulumi.Map)["spec"].(pulumi.Map)["automountServiceAccountToken"] = pulumi.Bool(false)
				return &pulumi.ResourceTransformResult{
					Props: args.Props,
					Opts:  args.Opts,
				}
			}
			return nil
		},
		// Add ImagePullSecrets to deployments
		func(_ context.Context, args *pulumi.ResourceTransformArgs) *pulumi.ResourceTransformResult {
			if args.Type == "kubernetes:apps/v1:Deployment" {
				args.Props["spec"].(pulumi.Map)["template"].(pulumi.Map)["spec"].(pulumi.Map)["imagePullSecrets"] = in.ImagePullSecrets().ApplyT(func(secrets []string) []pulumi.Map {
					if len(secrets) == 0 {
						return nil
					}
					refs := make([]pulumi.Map, len(secrets))
					for i, secret := range secrets {
						refs[i] = pulumi.Map{"name": pulumi.String(secret)}
					}
					return refs
				})
				return &pulumi.ResourceTransformResult{
					Props: args.Props,
					Opts:  args.Opts,
				}
			}
			return nil
		},
		// Add packet capture sidecar and volumes to deployments
		func(_ context.Context, args *pulumi.ResourceTransformArgs) *pulumi.ResourceTransformResult {
			if args.Type == "kubernetes:apps/v1:Deployment" {
				deploymentName := strings.TrimPrefix(args.Name, "kompose:default/")

				// Check if packet capture is enabled for this container
				in.PacketCapture().ApplyT(func(pc map[string]interface{}) error {
					enabled, hasKey := pc[deploymentName]
					if !hasKey {
						return nil
					}
					isEnabled, ok := enabled.(bool)
					if !ok || !isEnabled {
						return nil
					}

					// Get the identity and label for naming
					identity := in.Identity().ToStringOutput().ApplyT(func(id string) string {
						return id
					}).(pulumi.StringOutput)

					label := in.Label().ToStringPtrOutput().ApplyT(func(lbl *string) string {
						if lbl != nil {
							return *lbl
						}
						return ""
					}).(pulumi.StringOutput)

					// Enable share process namespace
					args.Props["spec"].(pulumi.Map)["template"].(pulumi.Map)["spec"].(pulumi.Map)["shareProcessNamespace"] = pulumi.Bool(true)

					// Get ports for this container from the deployment spec
					var portList string
					if containers, ok := args.Props["spec"].(pulumi.Map)["template"].(pulumi.Map)["spec"].(pulumi.Map)["containers"].(pulumi.Array); ok && len(containers) > 0 {
						if mainContainer, ok := containers[0].(pulumi.Map); ok {
							if ports, ok := mainContainer["ports"].(pulumi.Array); ok {
								portStrs := make([]string, 0, len(ports))
								for _, port := range ports {
									if portMap, ok := port.(pulumi.Map); ok {
										if containerPort, ok := portMap["containerPort"].(pulumi.Int); ok {
											protocol := "tcp"
											if proto, ok := portMap["protocol"].(pulumi.String); ok && proto != "" {
												protocol = strings.ToLower(string(proto))
											}
											portStrs = append(portStrs, fmt.Sprintf("%d:%s", containerPort, protocol))
										}
									}
								}
								portList = strings.Join(portStrs, ",")
							}
						}
					}

					// Build packet capture sidecar container
					sidecar := pulumi.Map{
						"name":            pulumi.Sprintf("%s-pcap", identity),
						"image":           pulumi.String("nicolaka/netshoot:v0.13"),
						"imagePullPolicy": pulumi.String("IfNotPresent"),
						"command":         pulumi.ToStringArray([]string{"/bin/bash", "/scripts/capture-daemon.sh"}),
						"env": pulumi.Array{
							pulumi.Map{"name": pulumi.String("CONTAINER_NAME"), "value": pulumi.String(deploymentName)},
							pulumi.Map{"name": pulumi.String("IDENTITY"), "value": identity},
							pulumi.Map{"name": pulumi.String("LABEL"), "value": label},
							pulumi.Map{"name": pulumi.String("PORTS"), "value": pulumi.String(portList)},
							pulumi.Map{"name": pulumi.String("CAPTURE_DIR"), "value": pulumi.String("/captures")},
						},
						"securityContext": pulumi.Map{
							"privileged": pulumi.Bool(true),
							"runAsUser":  pulumi.Int(0),
							"capabilities": pulumi.Map{
								"add": pulumi.ToStringArray([]string{"NET_RAW", "NET_ADMIN"}),
							},
						},
						"volumeMounts": pulumi.Array{
							pulumi.Map{
								"name":      pulumi.String("packet-captures"),
								"mountPath": pulumi.String("/captures"),
								"subPath":   pulumi.Sprintf("captures/%s/%s", identity, deploymentName),
							},
							pulumi.Map{
								"name":      pulumi.String("capture-script"),
								"mountPath": pulumi.String("/scripts"),
								"readOnly":  pulumi.Bool(true),
							},
						},
						"resources": pulumi.Map{
							"limits": pulumi.Map{
								"cpu":    pulumi.String("200m"),
								"memory": pulumi.String("256Mi"),
							},
							"requests": pulumi.Map{
								"cpu":    pulumi.String("100m"),
								"memory": pulumi.String("128Mi"),
							},
						},
					}

					// Add sidecar to containers
					if containers, ok := args.Props["spec"].(pulumi.Map)["template"].(pulumi.Map)["spec"].(pulumi.Map)["containers"].(pulumi.Array); ok {
						args.Props["spec"].(pulumi.Map)["template"].(pulumi.Map)["spec"].(pulumi.Map)["containers"] = append(containers, sidecar)
					}

					// Add volumes
					pcapPVCName := in.PacketCapturePVC().ToStringPtrOutput().ApplyT(func(p *string) string {
						if p != nil && *p != "" {
							return *p
						}
						return "pcap-core"
					}).(pulumi.StringOutput)

					pcapScriptName := pulumi.All(in.Identity(), in.Label()).ApplyT(func(all []any) string {
						id := all[0].(string)
						if lbl, ok := all[1].(string); ok && lbl != "" {
							return fmt.Sprintf("kmp-pcap-script-%s-%s", lbl, id)
						}
						return fmt.Sprintf("kmp-pcap-script-%s", id)
					}).(pulumi.StringOutput)

					// Create volumes as a pulumi.Array
					volumes := pulumi.Array{
						pulumi.Map{
							"name": pulumi.String("packet-captures"),
							"persistentVolumeClaim": pulumi.Map{
								"claimName": pcapPVCName,
							},
						},
						pulumi.Map{
							"name": pulumi.String("capture-script"),
							"configMap": pulumi.Map{
								"name":        pcapScriptName,
								"defaultMode": pulumi.Int(0755),
							},
						},
					}

					if existingVolumes, ok := args.Props["spec"].(pulumi.Map)["template"].(pulumi.Map)["spec"].(pulumi.Map)["volumes"].(pulumi.Array); ok {
						args.Props["spec"].(pulumi.Map)["template"].(pulumi.Map)["spec"].(pulumi.Map)["volumes"] = append(existingVolumes, volumes...)
					} else {
						args.Props["spec"].(pulumi.Map)["template"].(pulumi.Map)["spec"].(pulumi.Map)["volumes"] = volumes
					}

					return nil
				})

				return &pulumi.ResourceTransformResult{
					Props: args.Props,
					Opts:  args.Opts,
				}
			}
			return nil
		},
	}))

	// Generate Kubernetes resources
	objwg := sync.WaitGroup{}
	objwg.Add(1)
	kmp.cg, err = yamlv2.NewConfigGroup(ctx, "kompose", &yamlv2.ConfigGroupArgs{
		Yaml: in.YAML().ApplyT(func(yaml string) (man string) {
			man, _, _ = kompose(yaml)
			objwg.Done()
			return man
		}).(pulumi.StringOutput),
	}, opts...)
	if err != nil {
		return
	}

	// Generate Services and Ingresses whenever required
	keys := in.Ports().ApplyT(func(pbs map[string][]PortBinding) []string {
		out := make([]string, 0, len(pbs))
		for k := range pbs {
			out = append(out, k)
		}
		return out
	}).(pulumi.StringArrayOutput)
	objwg.Wait()
	for i := 0; i < lenP(keys); i++ {
		name := keys.Index(pulumi.Int(i))
		rawName := raw(name)
		pbs := in.Ports().MapIndex(name)

		svcs := corev1.ServiceMap{}.ToServiceMapOutput()
		svcSpecs := ServiceSpecMap{}.ToServiceSpecMapOutput()
		ings := netwv1.IngressMap{}.ToIngressMapOutput()
		ingSpecs := IngressSpecMap{}.ToIngressSpecMapOutput()

		for j := 0; j < pbs.Len(); j++ {
			p := pbs.Index(pulumi.Int(j))

			// Locate corresponding service
			svcwg := sync.WaitGroup{}
			svcwg.Add(1)
			var svc *corev1.Service
			kmp.cg.Resources.ApplyT(func(res []any) error {
				defer svcwg.Done()

				for _, r := range res {
					if s, ok := r.(*corev1.Service); ok {
						wg := sync.WaitGroup{}
						wg.Add(1)
						pulumi.All(s.Metadata.Name().Elem(), s.Spec, p).ApplyT(func(all []any) error {
							name := all[0].(string)
							spec := all[1].(corev1.ServiceSpec)
							pb := all[2].(PortBinding)

							svcProt := "TCP"
							if spec.Ports[0].Protocol != nil {
								svcProt = *spec.Ports[0].Protocol
							}

							if pb.Protocol == "" {
								pb.Protocol = "TCP"
							}

							if name == rawName && spec.Ports[0].Port == pb.Port && svcProt == pb.Protocol {
								svc = s
							}

							wg.Done()
							return nil
						})
						wg.Wait()
					}
				}
				return nil
			})
			svcwg.Wait()
			if svc == nil {
				// unit tests -> mocks{} -> *ConfigGroup is not evaluated -> no *corev1.Service
				continue
			}

			svcs = pulumi.All(svcs, p, svc).ApplyT(func(all []any) map[string]*corev1.Service {
				svcs := all[0].(map[string]*corev1.Service)
				pb := all[1].(PortBinding)
				svc := all[2].(*corev1.Service)

				prot := pb.Protocol
				if prot == "" {
					prot = "TCP"
				}

				svcs[fmt.Sprintf("%d/%s", pb.Port, prot)] = svc
				return svcs
			}).(corev1.ServiceMapOutput)
			svcSpecs = pulumi.All(svcSpecs, p, svc.Spec).ApplyT(func(all []any) map[string]corev1.ServiceSpec {
				svcs := all[0].(map[string]corev1.ServiceSpec)
				pb := all[1].(PortBinding)
				svc := all[2].(corev1.ServiceSpec)

				prot := pb.Protocol
				if prot == "" {
					prot = "TCP"
				}

				svcs[fmt.Sprintf("%d/%s", pb.Port, prot)] = svc
				return svcs
			}).(ServiceSpecMapOutput)

			switch p.ExposeType().Raw() {
			case ExposeLoadBalancer:
				// In the case of the LoadBalancer, the networking depends on the technology in use.
				// Considering this, it might be routed directly to the node/pod, or re-routed through
				// kubeproxy (or a CNI replacing it).
				//
				// That so, we cannot determine whether it is needed (or not) to allow ingress traffic
				// on this NodePort. Nonetheless, what we know in this context is that there is no port
				// reuse once one is assigned. Then, allowing ingress traffic on this NodePort won't
				// allow more traffic to come to the node, hence it is OK to allow ingress traffic.
				//
				// This rationale makes us deal with the serviceType=LoadBalancer as for a NodePort.
				// This operation might not be required, but is at least not affecting the security
				// posture out of what is intended.
				fallthrough

			case ExposeNodePort:
				// Service has already been covered by injecting the type through a transform
				ntp, err := netwv1.NewNetworkPolicy(ctx, fmt.Sprintf("emp-ntp-%s-%d", rawName, i), &netwv1.NetworkPolicyArgs{
					Metadata: metav1.ObjectMetaArgs{
						Labels: svc.Metadata.Labels(),
						Name: pulumi.All(in.Identity(), in.Label(), name, p.Port(), p.Protocol()).ApplyT(func(all []any) string {
							id := all[0].(string)
							name := all[2].(string)
							port := all[3].(int)
							prot := strings.ToLower(defaults(all[4], "TCP"))
							if lbl, ok := all[1].(string); ok && lbl != "" {
								return fmt.Sprintf("emp-ntp-%s-%s-%s-%d-%s", lbl, id, name, port, prot)
							}
							return fmt.Sprintf("emp-ntp-%s-%s-%d-%s", id, name, port, prot)
						}).(pulumi.StringOutput),
						Namespace: kmp.ns.Metadata.Name().Elem(),
					},
					Spec: netwv1.NetworkPolicySpecArgs{
						PodSelector: metav1.LabelSelectorArgs{
							MatchLabels: svc.Metadata.Labels(),
						},
						PolicyTypes: pulumi.ToStringArray([]string{
							"Ingress",
						}),
						Ingress: netwv1.NetworkPolicyIngressRuleArray{
							netwv1.NetworkPolicyIngressRuleArgs{
								From: netwv1.NetworkPolicyPeerArray{
									netwv1.NetworkPolicyPeerArgs{
										IpBlock: &netwv1.IPBlockArgs{
											Cidr: in.FromCIDR(),
										},
									},
								},
								Ports: netwv1.NetworkPolicyPortArray{
									netwv1.NetworkPolicyPortArgs{
										Port:     p.Port(),
										Protocol: p.Protocol(),
									},
								},
							},
						},
					},
				}, opts...)
				if err != nil {
					return err
				}
				kmp.ntps = append(kmp.ntps, ntp)

			case ExposeIngress:
				ing, err := netwv1.NewIngress(ctx, fmt.Sprintf("kmp-ing-%s-%d", rawName, j), &netwv1.IngressArgs{
					Metadata: metav1.ObjectMetaArgs{
						Annotations: func() pulumi.StringMapOutput {
							// If is exposed directly, plug it the annotations
							if slices.Contains([]ExposeType{
								ExposeNodePort,
								ExposeLoadBalancer,
							}, p.ExposeType().Raw()) {
								return p.Annotations()
							}
							return pulumi.StringMap{}.ToStringMapOutput()
						}(),
						Labels: svc.Metadata.Labels(),
						Name: pulumi.All(in.Identity(), in.Label(), name).ApplyT(func(all []any) string {
							id := all[0].(string)
							name := all[2].(string)
							if lbl, ok := all[1].(string); ok && lbl != "" {
								return fmt.Sprintf("emp-ing-%s-%s-%s", lbl, id, name)
							}
							return fmt.Sprintf("emp-ing-%s-%s", id, name)
						}).(pulumi.StringOutput),
						Namespace: kmp.ns.Metadata.Name().Elem(),
					},
					Spec: netwv1.IngressSpecArgs{
						Rules: netwv1.IngressRuleArray{
							netwv1.IngressRuleArgs{
								Host: pulumi.Sprintf("%s.%s", pulumi.All(in.Identity(), name, p).ApplyT(func(all []any) string {
									// Combine the identity, the container name and the port binding
									// to generate a pseudo-random string.
									id := all[0].(string)
									name := all[1].(string)
									p := all[2].(PortBinding)
									if p.Protocol == "" {
										p.Protocol = "TCP"
									}

									// Generate a hash of the seed, keep only first bytes (same lenght as
									// identity to avoid fingerprinting scenario on ingress name).
									seed := fmt.Sprintf("%s-%s-%d/%s", id, name, p.Port, p.Protocol)
									return randName(seed)[:len(id)]
								}).(pulumi.StringOutput), in.Hostname()),
								Http: netwv1.HTTPIngressRuleValueArgs{
									Paths: netwv1.HTTPIngressPathArray{
										netwv1.HTTPIngressPathArgs{
											Path:     pulumi.String("/"),
											PathType: pulumi.String("Prefix"),
											Backend: netwv1.IngressBackendArgs{
												Service: netwv1.IngressServiceBackendArgs{
													Name: name,
													Port: netwv1.ServiceBackendPortArgs{
														Number: p.Port(),
													},
												},
											},
										},
									},
								},
							},
						},
					},
				}, opts...)
				if err != nil {
					return err
				}
				ings = pulumi.All(ings, p, ing).ApplyT(func(all []any) map[string]*netwv1.Ingress {
					ings := all[0].(map[string]*netwv1.Ingress)
					pb := all[1].(PortBinding)
					ing := all[2].(*netwv1.Ingress)

					prot := pb.Protocol
					if prot == "" {
						prot = "TCP"
					}

					ings[fmt.Sprintf("%d/%s", pb.Port, prot)] = ing
					return ings
				}).(netwv1.IngressMapOutput)
				ingSpecs = pulumi.All(ingSpecs, p, ing.Spec).ApplyT(func(all []any) map[string]netwv1.IngressSpec {
					ings := all[0].(map[string]netwv1.IngressSpec)
					pb := all[1].(PortBinding)
					ing := all[2].(netwv1.IngressSpec)

					prot := pb.Protocol
					if prot == "" {
						prot = "TCP"
					}

					ings[fmt.Sprintf("%d/%s", pb.Port, prot)] = ing
					return ings
				}).(IngressSpecMapOutput)

				ntp, err := netwv1.NewNetworkPolicy(ctx, fmt.Sprintf("emp-ntp-%s-%d", rawName, i), &netwv1.NetworkPolicyArgs{
					Metadata: metav1.ObjectMetaArgs{
						Labels: svc.Metadata.Labels(),
						Name: pulumi.All(in.Identity(), in.Label(), name, p.Port(), p.Protocol()).ApplyT(func(all []any) string {
							id := all[0].(string)
							name := all[2].(string)
							port := all[3].(int)
							prot := strings.ToLower(defaults(all[4], "TCP"))
							if lbl, ok := all[1].(string); ok && lbl != "" {
								return fmt.Sprintf("emp-ntp-%s-%s-%s-%d-%s", lbl, id, name, port, prot)
							}
							return fmt.Sprintf("emp-ntp-%s-%s-%d-%s", id, name, port, prot)
						}).(pulumi.StringOutput),
						Namespace: kmp.ns.Metadata.Name().Elem(),
					},
					Spec: netwv1.NetworkPolicySpecArgs{
						PodSelector: metav1.LabelSelectorArgs{
							MatchLabels: svc.Metadata.Labels(),
						},
						PolicyTypes: pulumi.ToStringArray([]string{
							"Ingress",
						}),
						Ingress: netwv1.NetworkPolicyIngressRuleArray{
							netwv1.NetworkPolicyIngressRuleArgs{
								From: netwv1.NetworkPolicyPeerArray{
									netwv1.NetworkPolicyPeerArgs{
										NamespaceSelector: metav1.LabelSelectorArgs{
											MatchLabels: pulumi.StringMap{
												"kubernetes.io/metadata.name": in.IngressNamespace(),
											},
										},
										PodSelector: metav1.LabelSelectorArgs{
											MatchLabels: in.IngressLabels(),
										},
									},
								},
								Ports: netwv1.NetworkPolicyPortArray{
									netwv1.NetworkPolicyPortArgs{
										Port:     p.Port(),
										Protocol: p.Protocol(),
									},
								},
							},
						},
					},
				}, opts...)
				if err != nil {
					return err
				}
				kmp.ntps = append(kmp.ntps, ntp)
			}

			kmp.svcs = pulumi.All(kmp.svcs, name, svcs).ApplyT(func(all []any) map[string]map[string]*corev1.Service {
				svcs := all[0].(map[string]map[string]*corev1.Service)
				svcs[all[1].(string)] = all[2].(map[string]*corev1.Service)
				return svcs
			}).(ServiceMapMapOutput)
			kmp.svcSpecs = pulumi.All(kmp.svcSpecs, name, svcSpecs).ApplyT(func(all []any) map[string]map[string]corev1.ServiceSpec {
				svcs := all[0].(map[string]map[string]corev1.ServiceSpec)
				svcs[all[1].(string)] = all[2].(map[string]corev1.ServiceSpec)
				return svcs
			}).(ServiceSpecMapMapOutput)
			kmp.ings = pulumi.All(kmp.ings, name, ings).ApplyT(func(all []any) map[string]map[string]*netwv1.Ingress {
				ings := all[0].(map[string]map[string]*netwv1.Ingress)
				ings[all[1].(string)] = all[2].(map[string]*netwv1.Ingress)
				return ings
			}).(IngressMapMapOutput)
			kmp.ingSpecs = pulumi.All(kmp.ingSpecs, name, ingSpecs).ApplyT(func(all []any) map[string]map[string]netwv1.IngressSpec {
				ings := all[0].(map[string]map[string]netwv1.IngressSpec)
				ings[all[1].(string)] = all[2].(map[string]netwv1.IngressSpec)
				return ings
			}).(IngressSpecMapMapOutput)
		}
	}

	return
}

func (kmp *Kompose) outputs(ctx *pulumi.Context, in KomposeArgsOutput) error {
	keys := kmp.svcs.ApplyT(func(svcs ServiceMapMap) []string {
		out := make([]string, 0, len(svcs))
		for k := range svcs {
			out = append(out, k)
		}
		return out
	}).(pulumi.StringArrayOutput)

	for i := 0; i < lenP(keys); i++ {
		name := keys.Index(pulumi.Int(i))

		// => Service Node Port
		svcUrls := pulumi.All(in.Hostname(), kmp.svcSpecs.MapIndex(name)).ApplyT(func(all []any) map[string]string {
			hostname := all[0].(string)
			specs := all[1].(map[string]corev1.ServiceSpec)

			urls := map[string]string{}
			for k, spec := range specs {
				if spec.Type == nil {
					continue
				}
				switch *spec.Type {
				case "NodePort":
					np := spec.Ports[0].NodePort
					if np != nil {
						urls[k] = fmt.Sprintf("%s:%d", hostname, *np)
					}

				case "LoadBalancer":
					// Get both external ip and port.
					// If in a setup you don't need the port, just cut it out :)

					np := spec.Ports[0].NodePort
					if np == nil {
						// If the NodePort has not been assigned yet, we are in a preview
						// (or all ports in the range are exhausted), so we can skip waiting.
						continue
					}
					urls[k] = fmt.Sprintf("%s:%d", spec.ExternalIPs[0], *np)
				}
			}
			return urls
		}).(pulumi.StringMapOutput)

		// => Ingresses
		ingUrls := kmp.ingSpecs.MapIndex(name).ApplyT(func(specs map[string]netwv1.IngressSpec) map[string]string {
			urls := map[string]string{}
			for k, spec := range specs {
				h := spec.Rules[0].Host
				if h != nil {
					urls[k] = *h
				}
			}
			return urls
		}).(pulumi.StringMapOutput)

		kmp.URLs = pulumi.All(kmp.URLs, name, merge(svcUrls, ingUrls)).ApplyT(func(all []any) map[string]map[string]string {
			urls := all[0].(map[string]map[string]string)
			urls[all[1].(string)] = all[2].(map[string]string)
			return urls
		}).(pulumi.StringMapMapOutput)
	}

	return ctx.RegisterResourceOutputs(kmp, pulumi.Map{
		"urls": kmp.URLs,
	})
}

func kompose(yaml string) (string, []runtime.Object, error) {
	// XXX creating files is error-prone, but a good balance between no kompose SDK and incorporating kompose in CM install
	// Create temporary input file and output
	dc, err := os.CreateTemp(kdir, "dc")
	if err != nil {
		return "", nil, err
	}
	defer func() {
		_ = dc.Close()
	}()
	_, _ = dc.WriteString(yaml)

	out, err := os.CreateTemp(kdir, "manifest")
	if err != nil {
		return "", nil, err
	}
	defer func() {
		_ = out.Close()
	}()

	// Run kompose
	opts := kobject.ConvertOptions{
		InputFiles: []string{dc.Name()},
		OutFile:    out.Name(),
		// Default values in kompose CLI
		Build:      "none",
		Profiles:   []string{},
		Volumes:    "persistentVolumeClaim",
		Replicas:   1,
		Provider:   "kubernetes",
		YAMLIndent: 2,
	}
	objs, err := app.Convert(opts)
	if err != nil {
		log.Fatal(err)
	}

	man, err := io.ReadAll(out)
	if err != nil {
		return "", nil, err
	}
	return string(man), objs, nil
}

type KomposeArgsRaw struct {
	Identity string  `pulumi:"identity"`
	Label    *string `pulumi:"label"`
	Hostname string  `pulumi:"hostname"`

	// YAML content of a docker-compose.yaml file.
	YAML string `pulumi:"yaml"`

	Ports map[string][]PortBinding `pulumi:"ports"`

	// PacketCapture is a map of container names to whether packet capture is enabled.
	// If a container name is present and set to true, packet capture will be enabled for that container.
	PacketCapture map[string]bool `pulumi:"packetCapture"`

	FromCIDR           string            `pulumi:"fromCIDR"`
	IngressNamespace   string            `pulumi:"ingressNamespace"`
	IngressLabels      map[string]string `pulumi:"ingressLabels"`
	IngressAnnotations map[string]string `pulumi:"ingressAnnotations"`
	ImagePullSecrets   []string          `pulumi:"imagePullSecrets"`

	// PacketCapturePVC is the name of the shared PVC for packet captures.
	// If not set, defaults to "pcap-core".
	PacketCapturePVC *string `pulumi:"packetCapturePVC"`
}

type KomposeArgsInput interface {
	pulumi.Input

	ToKomposeArgsOutput() KomposeArgsOutput
	ToKomposeArgsOutputWithContext(context.Context) KomposeArgsOutput
}

type KomposeArgs struct {
	Identity pulumi.StringInput    `pulumi:"identity"`
	Label    pulumi.StringPtrInput `pulumi:"label"`
	Hostname pulumi.StringInput    `pulumi:"hostname"`

	// YAML content of a docker-compose.yaml file.
	YAML pulumi.StringInput `pulumi:"yaml"`

	// Ports define the binding per each image for how to expose
	// the containers.
	// Nonetheless, as per Kompose behavior, it creates 1 Service
	// for all ports, so the underlying Service type will be driven
	// by the latest NodePort or LoadBalancer defined in the array.
	// See #905 for more context.
	Ports PortBindingMapArrayInput `pulumi:"ports"`

	// PacketCapture is a map of container names to whether packet capture is enabled.
	PacketCapture pulumi.MapInput `pulumi:"packetCapture"`

	FromCIDR           pulumi.StringInput      `pulumi:"fromCIDR"`
	IngressNamespace   pulumi.StringInput      `pulumi:"ingressNamespace"`
	IngressLabels      pulumi.StringMapInput   `pulumi:"ingressLabels"`
	IngressAnnotations pulumi.StringMapInput   `pulumi:"ingressAnnotations"`
	ImagePullSecrets   pulumi.StringArrayInput `pulumi:"imagePullSecrets"`

	// PacketCapturePVC is the name of the shared PVC for packet captures.
	PacketCapturePVC pulumi.StringPtrInput `pulumi:"packetCapturePVC"`
}

func (KomposeArgs) ElementType() reflect.Type {
	return reflect.TypeOf((*KomposeArgsRaw)(nil)).Elem()
}

func (i KomposeArgs) ToKomposeArgsOutput() KomposeArgsOutput {
	return i.ToKomposeArgsOutputWithContext(context.Background())
}

func (i KomposeArgs) ToKomposeArgsOutputWithContext(ctx context.Context) KomposeArgsOutput {
	return pulumi.ToOutputWithContext(ctx, i).(KomposeArgsOutput)
}

type KomposeArgsOutput struct{ *pulumi.OutputState }

func (KomposeArgsOutput) ElementType() reflect.Type {
	return reflect.TypeOf((*KomposeArgsRaw)(nil)).Elem()
}

func (o KomposeArgsOutput) Identity() pulumi.StringOutput {
	return o.ApplyT(func(args KomposeArgsRaw) string {
		return args.Identity
	}).(pulumi.StringOutput)
}

func (o KomposeArgsOutput) Label() pulumi.StringPtrOutput {
	return o.ApplyT(func(args KomposeArgsRaw) *string {
		return args.Label
	}).(pulumi.StringPtrOutput)
}

func (o KomposeArgsOutput) Hostname() pulumi.StringOutput {
	return o.ApplyT(func(args KomposeArgsRaw) string {
		return args.Hostname
	}).(pulumi.StringOutput)
}

func (o KomposeArgsOutput) YAML() pulumi.StringOutput {
	return o.ApplyT(func(k KomposeArgsRaw) string {
		return k.YAML
	}).(pulumi.StringOutput)
}

func (o KomposeArgsOutput) Ports() PortBindingMapArrayOutput {
	return o.ApplyT(func(k KomposeArgsRaw) map[string][]PortBinding {
		return k.Ports
	}).(PortBindingMapArrayOutput)
}

func (o KomposeArgsOutput) FromCIDR() pulumi.StringOutput {
	return o.ApplyT(func(args KomposeArgsRaw) string {
		if args.FromCIDR == "" {
			return defaultCIDR
		}
		return args.FromCIDR
	}).(pulumi.StringOutput)
}

func (o KomposeArgsOutput) IngressNamespace() pulumi.StringOutput {
	return o.ApplyT(func(args KomposeArgsRaw) string {
		return args.IngressNamespace
	}).(pulumi.StringOutput)
}

func (o KomposeArgsOutput) IngressLabels() pulumi.StringMapOutput {
	return o.ApplyT(func(args KomposeArgsRaw) map[string]string {
		return args.IngressLabels
	}).(pulumi.StringMapOutput)
}

func (o KomposeArgsOutput) IngressAnnotations() pulumi.StringMapOutput {
	return o.ApplyT(func(args KomposeArgsRaw) map[string]string {
		return args.IngressAnnotations
	}).(pulumi.StringMapOutput)
}

func (o KomposeArgsOutput) ImagePullSecrets() pulumi.StringArrayOutput {
	return o.ApplyT(func(args KomposeArgsRaw) []string {
		return args.ImagePullSecrets
	}).(pulumi.StringArrayOutput)
}

func (o KomposeArgsOutput) PacketCapture() pulumi.MapOutput {
	return o.ApplyT(func(args KomposeArgsRaw) map[string]interface{} {
		if args.PacketCapture == nil {
			return nil
		}
		out := make(map[string]interface{}, len(args.PacketCapture))
		for k, v := range args.PacketCapture {
			out[k] = v
		}
		return out
	}).(pulumi.MapOutput)
}

func (o KomposeArgsOutput) PacketCapturePVC() pulumi.StringPtrOutput {
	return o.ApplyT(func(args KomposeArgsRaw) *string {
		return args.PacketCapturePVC
	}).(pulumi.StringPtrOutput)
}

func init() {
	pulumi.RegisterInputType(reflect.TypeOf((*KomposeArgsInput)(nil)).Elem(), KomposeArgs{})
	pulumi.RegisterOutputType(KomposeArgsOutput{})
}
