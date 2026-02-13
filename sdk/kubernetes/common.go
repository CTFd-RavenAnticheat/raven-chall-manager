package kubernetes

import (
	"crypto/sha1"
	"encoding/hex"
	"strconv"
	"sync"

	"github.com/pulumi/pulumi/sdk/v3/go/pulumi"
)

const (
	defaultCIDR = "0.0.0.0/0"
)

type DepCon struct {
	name string
	deps []string
}

var _ Resource = (*DepCon)(nil)

func (d *DepCon) GetID() string             { return d.name }
func (d *DepCon) GetDependencies() []string { return d.deps }

// randName is a pseudo-random name generator. It does not include
// random under the hood thus is reproducible.
func randName(seed string) string {
	h := sha1.New()
	if _, err := h.Write([]byte(seed)); err != nil {
		// This will happen only if FIPS compliance is turned on
		panic(err)
	}
	return hex.EncodeToString(h.Sum(nil))
}

func ptr[T any](t T) *T {
	return &t
}

func defaults[T comparable](v any, def T) T {
	if v == nil {
		return def
	}
	if nv, ok := v.(T); ok {
		if nv == *new(T) {
			return def
		}
		return nv
	}
	panic("invalid setup")
}

func merge(all ...pulumi.StringMapOutput) pulumi.StringMapOutput {
	if len(all) == 0 {
		return pulumi.StringMap{}.ToStringMapOutput()
	}
	out := all[0]
	for _, b := range all[1:] {
		out = pulumi.All(out, b).ApplyT(func(all []any) map[string]string {
			o := all[0].(map[string]string)
			no := all[1].(map[string]string)
			for k, v := range no {
				o[k] = v
			}
			return o
		}).(pulumi.StringMapOutput)
	}
	return out
}

func raw(o pulumi.StringOutput) string {
	var s string
	wg := sync.WaitGroup{}
	wg.Add(1)
	o.ApplyT(func(v string) error {
		s = v
		wg.Done()
		return nil
	})
	wg.Wait()
	return s
}

func lenP(o pulumi.StringArrayOutput) int {
	var l int
	wg := sync.WaitGroup{}
	wg.Add(1)
	o.ApplyT(func(v []string) error {
		l = len(v)
		wg.Done()
		return nil
	})
	wg.Wait()
	return l
}

// divideResource divides a Kubernetes resource quantity string by a divisor.
// Supports CPU (m suffix or no suffix) and memory (Ki, Mi, Gi, etc.).
// Examples: "500m" / 6 = "83m", "256Mi" / 6 = "42Mi", "1" / 6 = "166m"
func divideResource(resource string, divisor int) string {
	if resource == "" || divisor <= 0 {
		return resource
	}

	// Parse CPU resources (with 'm' suffix for millicores)
	if len(resource) > 1 && resource[len(resource)-1] == 'm' {
		// Millicores: "500m" -> 500
		if val, err := strconv.Atoi(resource[:len(resource)-1]); err == nil {
			result := val / divisor
			if result < 1 {
				result = 1 // Minimum 1m
			}
			return strconv.Itoa(result) + "m"
		}
	}

	// Parse memory resources (Ki, Mi, Gi, Ti, Pi, Ei)
	suffixes := []string{"Ei", "Pi", "Ti", "Gi", "Mi", "Ki"}
	for _, suffix := range suffixes {
		if len(resource) > len(suffix) && resource[len(resource)-len(suffix):] == suffix {
			if val, err := strconv.Atoi(resource[:len(resource)-len(suffix)]); err == nil {
				result := val / divisor
				if result < 1 {
					result = 1 // Minimum 1 unit
				}
				return strconv.Itoa(result) + suffix
			}
		}
	}

	// Parse plain CPU cores: "1" or "2" -> convert to millicores
	if val, err := strconv.Atoi(resource); err == nil {
		millicores := (val * 1000) / divisor
		if millicores < 1 {
			millicores = 1
		}
		return strconv.Itoa(millicores) + "m"
	}

	// If we can't parse it, return original
	return resource
}
