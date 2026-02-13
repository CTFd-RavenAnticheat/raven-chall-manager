package global

var (
	Version = ""
)

// Configuration holds the parameters that are shared across submodules.
type Configuration struct {
	Directory string
	Cache     string
	LogLevel  string

	// PulumiTimeout is the maximum time (in seconds) to wait for Pulumi operations (Up, Destroy, etc.)
	// before timing out. Default is 120 seconds (2 minutes) to prevent catastrophic blocking.
	// Set to 0 to disable timeout (not recommended for production).
	PulumiTimeout int

	Otel struct {
		Tracing     bool
		ServiceName string
	}

	Etcd struct {
		Endpoint string
		Username string
		Password string
	}

	OCI struct {
		Insecure bool
		Username string
		Password string
	}
}

var (
	Conf Configuration
)
