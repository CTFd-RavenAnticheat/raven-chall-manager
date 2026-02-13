package challenge

import (
	"archive/zip"
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/ctfer-io/chall-manager/global"
	"github.com/ctfer-io/chall-manager/pkg/scenario"
	"go.uber.org/zap"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/emptypb"
	"google.golang.org/protobuf/types/known/timestamppb"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
)

// getKubernetesClient creates a Kubernetes client using in-cluster config or kubeconfig
func getKubernetesClient() (*kubernetes.Clientset, error) {
	// Try in-cluster config first
	config, err := rest.InClusterConfig()
	if err != nil {
		// Fall back to kubeconfig
		kubeconfig := os.Getenv("KUBECONFIG")
		if kubeconfig == "" {
			home, _ := os.UserHomeDir()
			kubeconfig = home + "/.kube/config"
		}
		config, err = clientcmd.BuildConfigFromFlags("", kubeconfig)
		if err != nil {
			return nil, fmt.Errorf("failed to create kubernetes config: %w", err)
		}
	}

	// Fix for kind clusters: replace 0.0.0.0 with 127.0.0.1
	// 0.0.0.0 is used by kind for the API server bind address, but clients
	// cannot connect to 0.0.0.0. We replace it with 127.0.0.1.
	// Note: This may cause certificate validation issues if the cluster's
	// certificate doesn't include 127.0.0.1. In that case, users should
	// update their kubeconfig to use the Docker network IP instead.
	if strings.Contains(config.Host, "://0.0.0.0:") {
		config.Host = strings.Replace(config.Host, "://0.0.0.0:", "://127.0.0.1:", 1)
	}

	clientset, err := kubernetes.NewForConfig(config)
	if err != nil {
		return nil, fmt.Errorf("failed to create kubernetes client: %w", err)
	}

	return clientset, nil
}

// getNamespace returns the namespace from the request or the default
func getNamespace(reqNamespace string) string {
	if reqNamespace != "" {
		return reqNamespace
	}
	// Get namespace from environment or use default
	namespace := os.Getenv("KUBERNETES_TARGET_NAMESPACE")
	if namespace != "" {
		return namespace
	}
	return "chall-manager"
}

// SecretManagerService implements the SecretManager gRPC service.
type SecretManagerService struct {
	UnimplementedSecretManagerServer
}

// NewSecretManagerService creates a new SecretManager service.
func NewSecretManagerService() *SecretManagerService {
	return &SecretManagerService{}
}

// ListSecrets lists all secrets in the challenge namespace.
func (s *SecretManagerService) ListSecrets(ctx context.Context, req *ListSecretsRequest) (*ListSecretsResponse, error) {
	logger := global.Log()
	logger.Info(ctx, "listing secrets")

	namespace := getNamespace(req.GetNamespace())

	// Get Kubernetes client
	k8sClient, err := getKubernetesClient()
	if err != nil {
		logger.Error(ctx, "failed to get kubernetes client", zap.Error(err))
		return nil, status.Errorf(codes.Internal, "failed to get kubernetes client: %v", err)
	}

	// List secrets
	secretList, err := k8sClient.CoreV1().Secrets(namespace).List(ctx, metav1.ListOptions{})
	if err != nil {
		logger.Error(ctx, "failed to list secrets", zap.Error(err))
		return nil, status.Errorf(codes.Internal, "failed to list secrets: %v", err)
	}

	// Convert to response
	secrets := make([]*Secret, 0, len(secretList.Items))
	for _, secret := range secretList.Items {
		dataKeys := make([]string, 0, len(secret.Data))
		for key := range secret.Data {
			dataKeys = append(dataKeys, key)
		}

		secrets = append(secrets, &Secret{
			Name:             secret.Name,
			Type:             string(secret.Type),
			Namespace:        secret.Namespace,
			CreatedAt:        timestamppb.New(secret.CreationTimestamp.Time),
			DataKeys:         dataKeys,
			UsedByChallenges: []string{}, // TODO: Query challenges using this secret
		})
	}

	logger.Info(ctx, "listed secrets successfully", zap.Int("count", len(secrets)))
	return &ListSecretsResponse{Secrets: secrets}, nil
}

// CreateDockerRegistrySecret creates a Docker registry secret.
func (s *SecretManagerService) CreateDockerRegistrySecret(ctx context.Context, req *CreateDockerRegistrySecretRequest) (*Secret, error) {
	logger := global.Log()
	logger.Info(ctx, "creating docker registry secret", zap.String("name", req.GetName()))

	// Validate request
	if req.GetName() == "" || req.GetServer() == "" || req.GetUsername() == "" || req.GetPassword() == "" {
		return nil, status.Errorf(codes.InvalidArgument, "name, server, username, and password are required")
	}

	namespace := getNamespace(req.GetNamespace())

	// Get Kubernetes client
	k8sClient, err := getKubernetesClient()
	if err != nil {
		logger.Error(ctx, "failed to get kubernetes client", zap.Error(err))
		return nil, status.Errorf(codes.Internal, "failed to get kubernetes client: %v", err)
	}

	// Create docker config
	auth := base64.StdEncoding.EncodeToString([]byte(fmt.Sprintf("%s:%s", req.GetUsername(), req.GetPassword())))
	dockerConfig := map[string]interface{}{
		"auths": map[string]interface{}{
			req.GetServer(): map[string]interface{}{
				"username": req.GetUsername(),
				"password": req.GetPassword(),
				"email":    req.GetEmail(),
				"auth":     auth,
			},
		},
	}

	dockerConfigJSON, err := json.Marshal(dockerConfig)
	if err != nil {
		logger.Error(ctx, "failed to marshal docker config", zap.Error(err))
		return nil, status.Errorf(codes.Internal, "failed to marshal docker config: %v", err)
	}

	// Create secret
	secret := &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{
			Name:      req.GetName(),
			Namespace: namespace,
			Labels: map[string]string{
				"app.kubernetes.io/managed-by":       "chall-manager",
				"chall-manager.ctfer.io/secret-type": "docker-registry",
			},
		},
		Type: corev1.SecretTypeDockerConfigJson,
		Data: map[string][]byte{
			".dockerconfigjson": dockerConfigJSON,
		},
	}

	// Create the secret in Kubernetes
	createdSecret, err := k8sClient.CoreV1().Secrets(namespace).Create(ctx, secret, metav1.CreateOptions{})
	if err != nil {
		logger.Error(ctx, "failed to create secret", zap.Error(err))
		return nil, status.Errorf(codes.Internal, "failed to create secret: %v", err)
	}

	logger.Info(ctx, "created docker registry secret successfully", zap.String("name", createdSecret.Name))

	return &Secret{
		Name:             createdSecret.Name,
		Type:             string(createdSecret.Type),
		Namespace:        createdSecret.Namespace,
		CreatedAt:        timestamppb.New(createdSecret.CreationTimestamp.Time),
		DataKeys:         []string{".dockerconfigjson"},
		UsedByChallenges: []string{},
	}, nil
}

// CreateGenericSecret creates a generic opaque secret.
func (s *SecretManagerService) CreateGenericSecret(ctx context.Context, req *CreateGenericSecretRequest) (*Secret, error) {
	logger := global.Log()
	logger.Info(ctx, "creating generic secret", zap.String("name", req.GetName()))

	// Validate request
	if req.GetName() == "" {
		return nil, status.Errorf(codes.InvalidArgument, "name is required")
	}

	if len(req.GetData()) == 0 {
		return nil, status.Errorf(codes.InvalidArgument, "data is required")
	}

	namespace := getNamespace(req.GetNamespace())

	// Get Kubernetes client
	k8sClient, err := getKubernetesClient()
	if err != nil {
		logger.Error(ctx, "failed to get kubernetes client", zap.Error(err))
		return nil, status.Errorf(codes.Internal, "failed to get kubernetes client: %v", err)
	}

	// Convert data to byte arrays
	data := make(map[string][]byte)
	dataKeys := make([]string, 0, len(req.GetData()))
	for key, value := range req.GetData() {
		data[key] = []byte(value)
		dataKeys = append(dataKeys, key)
	}

	// Create secret
	secret := &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{
			Name:      req.GetName(),
			Namespace: namespace,
			Labels: map[string]string{
				"app.kubernetes.io/managed-by":       "chall-manager",
				"chall-manager.ctfer.io/secret-type": "generic",
			},
		},
		Type: corev1.SecretTypeOpaque,
		Data: data,
	}

	// Create the secret in Kubernetes
	createdSecret, err := k8sClient.CoreV1().Secrets(namespace).Create(ctx, secret, metav1.CreateOptions{})
	if err != nil {
		logger.Error(ctx, "failed to create secret", zap.Error(err))
		return nil, status.Errorf(codes.Internal, "failed to create secret: %v", err)
	}

	logger.Info(ctx, "created generic secret successfully", zap.String("name", createdSecret.Name))

	return &Secret{
		Name:             createdSecret.Name,
		Type:             string(createdSecret.Type),
		Namespace:        createdSecret.Namespace,
		CreatedAt:        timestamppb.New(createdSecret.CreationTimestamp.Time),
		DataKeys:         dataKeys,
		UsedByChallenges: []string{},
	}, nil
}

// CreateTLSSecret creates a TLS secret.
func (s *SecretManagerService) CreateTLSSecret(ctx context.Context, req *CreateTLSSecretRequest) (*Secret, error) {
	logger := global.Log()
	logger.Info(ctx, "creating TLS secret", zap.String("name", req.GetName()))

	// Validate request
	if req.GetName() == "" || req.GetCert() == "" || req.GetKey() == "" {
		return nil, status.Errorf(codes.InvalidArgument, "name, cert, and key are required")
	}

	namespace := getNamespace(req.GetNamespace())

	// Get Kubernetes client
	k8sClient, err := getKubernetesClient()
	if err != nil {
		logger.Error(ctx, "failed to get kubernetes client", zap.Error(err))
		return nil, status.Errorf(codes.Internal, "failed to get kubernetes client: %v", err)
	}

	// Create secret
	secret := &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{
			Name:      req.GetName(),
			Namespace: namespace,
			Labels: map[string]string{
				"app.kubernetes.io/managed-by":       "chall-manager",
				"chall-manager.ctfer.io/secret-type": "tls",
			},
		},
		Type: corev1.SecretTypeTLS,
		Data: map[string][]byte{
			"tls.crt": []byte(req.GetCert()),
			"tls.key": []byte(req.GetKey()),
		},
	}

	// Create the secret in Kubernetes
	createdSecret, err := k8sClient.CoreV1().Secrets(namespace).Create(ctx, secret, metav1.CreateOptions{})
	if err != nil {
		logger.Error(ctx, "failed to create secret", zap.Error(err))
		return nil, status.Errorf(codes.Internal, "failed to create secret: %v", err)
	}

	logger.Info(ctx, "created TLS secret successfully", zap.String("name", createdSecret.Name))

	return &Secret{
		Name:             createdSecret.Name,
		Type:             string(createdSecret.Type),
		Namespace:        createdSecret.Namespace,
		CreatedAt:        timestamppb.New(createdSecret.CreationTimestamp.Time),
		DataKeys:         []string{"tls.crt", "tls.key"},
		UsedByChallenges: []string{},
	}, nil
}

// DeleteSecret deletes a secret.
func (s *SecretManagerService) DeleteSecret(ctx context.Context, req *DeleteSecretRequest) (*emptypb.Empty, error) {
	logger := global.Log()
	logger.Info(ctx, "deleting secret", zap.String("name", req.GetName()))

	// Validate request
	if req.GetName() == "" {
		return nil, status.Errorf(codes.InvalidArgument, "name is required")
	}

	namespace := getNamespace(req.GetNamespace())

	// Get Kubernetes client
	k8sClient, err := getKubernetesClient()
	if err != nil {
		logger.Error(ctx, "failed to get kubernetes client", zap.Error(err))
		return nil, status.Errorf(codes.Internal, "failed to get kubernetes client: %v", err)
	}

	// Delete the secret
	err = k8sClient.CoreV1().Secrets(namespace).Delete(ctx, req.GetName(), metav1.DeleteOptions{})
	if err != nil {
		logger.Error(ctx, "failed to delete secret", zap.Error(err))
		return nil, status.Errorf(codes.Internal, "failed to delete secret: %v", err)
	}

	logger.Info(ctx, "deleted secret successfully", zap.String("name", req.GetName()))
	return &emptypb.Empty{}, nil
}

// TestRegistryConnection tests registry credentials without creating a secret.
func (s *SecretManagerService) TestRegistryConnection(ctx context.Context, req *TestRegistryConnectionRequest) (*TestRegistryConnectionResponse, error) {
	logger := global.Log()
	logger.Info(ctx, "testing registry connection", zap.String("server", req.GetServer()))

	// Validate request
	if req.GetServer() == "" || req.GetUsername() == "" || req.GetPassword() == "" {
		return nil, status.Errorf(codes.InvalidArgument, "server, username, and password are required")
	}

	// Try to connect to registry
	client := &http.Client{Timeout: 10 * time.Second}
	url := fmt.Sprintf("https://%s/v2/", req.GetServer())

	request, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		logger.Error(ctx, "failed to create request", zap.Error(err))
		return &TestRegistryConnectionResponse{
			Success: false,
			Message: fmt.Sprintf("Failed to create request: %v", err),
		}, nil
	}

	// Add basic auth
	auth := base64.StdEncoding.EncodeToString([]byte(fmt.Sprintf("%s:%s", req.GetUsername(), req.GetPassword())))
	request.Header.Set("Authorization", "Basic "+auth)

	response, err := client.Do(request)
	if err != nil {
		logger.Warn(ctx, "registry connection test failed", zap.Error(err))
		return &TestRegistryConnectionResponse{
			Success: false,
			Message: fmt.Sprintf("Failed to connect to registry: %v", err),
		}, nil
	}
	defer response.Body.Close()

	// Check response
	if response.StatusCode == http.StatusOK || response.StatusCode == http.StatusUnauthorized {
		logger.Info(ctx, "registry connection test successful")
		return &TestRegistryConnectionResponse{
			Success:       true,
			Message:       fmt.Sprintf("Successfully connected to %s", req.GetServer()),
			Authenticated: response.StatusCode == http.StatusOK,
		}, nil
	}

	logger.Warn(ctx, "registry returned unexpected status", zap.Int("status", response.StatusCode))
	return &TestRegistryConnectionResponse{
		Success:       true,
		Message:       fmt.Sprintf("Connected to registry but received status %d", response.StatusCode),
		Authenticated: false,
	}, nil
}

// PushScenario pushes a scenario ZIP to an OCI registry.
func (s *SecretManagerService) PushScenario(ctx context.Context, req *PushScenarioRequest) (*PushScenarioResponse, error) {
	logger := global.Log()
	logger.Info(ctx, "pushing scenario to registry", zap.String("reference", req.GetReference()))

	// Validate request
	if len(req.GetScenarioZip()) == 0 {
		return nil, status.Errorf(codes.InvalidArgument, "scenario_zip is required")
	}
	if req.GetReference() == "" {
		return nil, status.Errorf(codes.InvalidArgument, "reference is required")
	}

	// Use globally configured OCI credentials
	username := global.Conf.OCI.Username
	password := global.Conf.OCI.Password
	if username == "" || password == "" {
		return nil, status.Errorf(codes.InvalidArgument, "OCI registry credentials not configured. Set OCI_USERNAME and OCI_PASSWORD environment variables")
	}

	// Create temporary directory for extracting ZIP
	tmpDir, err := os.MkdirTemp("", "scenario-push-*")
	if err != nil {
		logger.Error(ctx, "failed to create temp directory", zap.Error(err))
		return nil, status.Errorf(codes.Internal, "failed to create temp directory: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	// Extract ZIP to temp directory
	zipReader, err := zip.NewReader(bytes.NewReader(req.GetScenarioZip()), int64(len(req.GetScenarioZip())))
	if err != nil {
		logger.Error(ctx, "failed to read ZIP archive", zap.Error(err))
		return nil, status.Errorf(codes.InvalidArgument, "invalid ZIP archive: %v", err)
	}

	for _, file := range zipReader.File {
		path := filepath.Join(tmpDir, file.Name)

		// Security: prevent directory traversal
		if !strings.HasPrefix(path, filepath.Clean(tmpDir)+string(os.PathSeparator)) {
			logger.Error(ctx, "invalid file path in ZIP", zap.String("path", file.Name))
			return nil, status.Errorf(codes.InvalidArgument, "invalid file path in ZIP: %s", file.Name)
		}

		if file.FileInfo().IsDir() {
			os.MkdirAll(path, file.Mode())
			continue
		}

		if err := os.MkdirAll(filepath.Dir(path), os.ModePerm); err != nil {
			logger.Error(ctx, "failed to create directory", zap.Error(err))
			return nil, status.Errorf(codes.Internal, "failed to create directory: %v", err)
		}

		outFile, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, file.Mode())
		if err != nil {
			logger.Error(ctx, "failed to create file", zap.Error(err))
			return nil, status.Errorf(codes.Internal, "failed to create file: %v", err)
		}

		rc, err := file.Open()
		if err != nil {
			outFile.Close()
			return nil, status.Errorf(codes.Internal, "failed to open ZIP entry: %v", err)
		}

		_, err = io.Copy(outFile, rc)
		rc.Close()
		outFile.Close()

		if err != nil {
			return nil, status.Errorf(codes.Internal, "failed to extract file: %v", err)
		}
	}

	logger.Info(ctx, "extracted scenario ZIP", zap.String("dir", tmpDir))

	// Push to OCI registry using the scenario package
	if err := scenario.EncodeOCI(ctx, req.GetReference(), tmpDir, global.Conf.OCI.Insecure, username, password); err != nil {
		logger.Error(ctx, "failed to push scenario", zap.Error(err))
		return nil, status.Errorf(codes.Internal, "failed to push scenario: %v", err)
	}

	logger.Info(ctx, "successfully pushed scenario", zap.String("reference", req.GetReference()))

	return &PushScenarioResponse{
		Success:   true,
		Reference: req.GetReference(),
		Message:   fmt.Sprintf("Successfully pushed scenario to %s", req.GetReference()),
	}, nil
}
