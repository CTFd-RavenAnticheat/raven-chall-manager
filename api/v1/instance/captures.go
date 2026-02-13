package instance

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strings"
	"time"

	"github.com/ctfer-io/chall-manager/pkg/fs"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/kubernetes/scheme"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
	"k8s.io/client-go/tools/remotecommand"
)

// getKubernetesClient creates a Kubernetes client using in-cluster config or kubeconfig
func getKubernetesClient() (*kubernetes.Clientset, *rest.Config, error) {
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
			return nil, nil, fmt.Errorf("failed to create kubernetes config: %w", err)
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
		return nil, nil, fmt.Errorf("failed to create kubernetes client: %w", err)
	}

	return clientset, config, nil
}

// execInPod executes a command in a pod container and returns the output
func execInPod(ctx context.Context, clientset *kubernetes.Clientset, config *rest.Config, namespace, podName, containerName string, command []string) (string, error) {
	req := clientset.CoreV1().RESTClient().Post().
		Resource("pods").
		Name(podName).
		Namespace(namespace).
		SubResource("exec").
		VersionedParams(&corev1.PodExecOptions{
			Container: containerName,
			Command:   command,
			Stdout:    true,
			Stderr:    true,
		}, scheme.ParameterCodec)

	exec, err := remotecommand.NewSPDYExecutor(config, "POST", req.URL())
	if err != nil {
		return "", fmt.Errorf("failed to create executor: %w", err)
	}

	var stdout, stderr bytes.Buffer
	err = exec.StreamWithContext(ctx, remotecommand.StreamOptions{
		Stdout: &stdout,
		Stderr: &stderr,
	})
	if err != nil {
		return "", fmt.Errorf("failed to execute command: %w (stderr: %s)", err, stderr.String())
	}

	return stdout.String(), nil
}

// execInPodStream executes a command in a pod container and streams the output
func execInPodStream(ctx context.Context, clientset *kubernetes.Clientset, config *rest.Config, namespace, podName, containerName string, command []string, writer io.Writer) error {
	req := clientset.CoreV1().RESTClient().Post().
		Resource("pods").
		Name(podName).
		Namespace(namespace).
		SubResource("exec").
		VersionedParams(&corev1.PodExecOptions{
			Container: containerName,
			Command:   command,
			Stdout:    true,
			Stderr:    true,
		}, scheme.ParameterCodec)

	exec, err := remotecommand.NewSPDYExecutor(config, "POST", req.URL())
	if err != nil {
		return fmt.Errorf("failed to create executor: %w", err)
	}

	var stderr bytes.Buffer
	err = exec.StreamWithContext(ctx, remotecommand.StreamOptions{
		Stdout: writer,
		Stderr: &stderr,
	})
	if err != nil {
		return fmt.Errorf("failed to execute command: %w (stderr: %s)", err, stderr.String())
	}

	return nil
}

func (man *Manager) ListCaptureSessions(ctx context.Context, req *ListCaptureSessionsRequest) (*ListCaptureSessionsResponse, error) {
	if req.ChallengeId == "" {
		return nil, status.Error(codes.InvalidArgument, "challenge_id is required")
	}

	// Get Kubernetes client
	clientset, config, err := getKubernetesClient()
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to create kubernetes client: %v", err)
	}

	// Get namespace from environment or use default
	namespace := os.Getenv("KUBERNETES_TARGET_NAMESPACE")
	if namespace == "" {
		namespace = "default"
	}

	// Determine search path based on source_id
	searchPath := fmt.Sprintf("/captures/captures/%s", req.ChallengeId)
	if req.SourceId != "" {
		instanceId, err := fs.FindInstance(req.ChallengeId, req.SourceId)
		if err != nil {
			return nil, status.Errorf(codes.NotFound, "instance not found: %v", err)
		}
		searchPath = fmt.Sprintf("/captures/captures/%s/%s", req.ChallengeId, instanceId)
	}

	podName, containerName := "pcap-core-pod", "recovery"
	// Try to find all sessions.json files within the scoped path
	output, err := execInPod(ctx, clientset, config, namespace, podName, containerName,
		[]string{"sh", "-c", fmt.Sprintf("find %s -name sessions.json -exec cat {} +", searchPath)})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to read sessions metadata: %v", err)
	}

	// The output might be multiple JSON objects if using shared PVCs: {"sessions":[...]}{"sessions":[...]}
	// We need to parse them individually.
	allSessions := []*CaptureSessionInfo{}
	dec := json.NewDecoder(strings.NewReader(output))
	for dec.More() {
		var metadata struct {
			Sessions []struct {
				SessionID   string `json:"session_id"`
				Container   string `json:"container"`
				StartTime   string `json:"start_time"`
				EndTime     string `json:"end_time"`
				FilePath    string `json:"file_path"`
				PacketCount int64  `json:"packet_count"`
				FileSize    int64  `json:"file_size"`
			} `json:"sessions"`
		}
		if err := dec.Decode(&metadata); err != nil {
			return nil, status.Errorf(codes.Internal, "failed to decode sessions metadata: %v", err)
		}

		for _, s := range metadata.Sessions {
			info := &CaptureSessionInfo{
				SessionId:   s.SessionID,
				Container:   s.Container,
				FilePath:    s.FilePath,
				PacketCount: s.PacketCount,
				FileSize:    s.FileSize,
			}
			if t, err := time.Parse(time.RFC3339, s.StartTime); err == nil {
				info.StartTime = timestamppb.New(t)
			}
			if t, err := time.Parse(time.RFC3339, s.EndTime); err == nil {
				info.EndTime = timestamppb.New(t)
			}
			allSessions = append(allSessions, info)
		}
	}

	return &ListCaptureSessionsResponse{
		Sessions: allSessions,
	}, nil
}

func (man *Manager) DownloadCaptures(req *DownloadCapturesRequest, stream InstanceManager_DownloadCapturesServer) error {
	if req.ChallengeId == "" {
		return status.Error(codes.InvalidArgument, "challenge_id is required")
	}
	ctx := stream.Context()

	// Get Kubernetes client
	clientset, config, err := getKubernetesClient()
	if err != nil {
		return status.Errorf(codes.Internal, "failed to create kubernetes client: %v", err)
	}

	// Get namespace from environment or use default
	namespace := os.Getenv("KUBERNETES_TARGET_NAMESPACE")
	if namespace == "" {
		namespace = "default"
	}

	podName, containerName := "pcap-core-pod", "recovery"

	// Create a pipe to stream tar output
	pr, pw := io.Pipe()

	// Determine search path based on source_id
	searchPath := fmt.Sprintf("/captures/captures/%s", req.ChallengeId)
	if req.SourceId != "" {
		instanceId, err := fs.FindInstance(req.ChallengeId, req.SourceId)
		if err != nil {
			return status.Errorf(codes.NotFound, "instance not found: %v", err)
		}
		searchPath = fmt.Sprintf("/captures/captures/%s/%s", req.ChallengeId, instanceId)
	}

	// Start tar command in background
	errChan := make(chan error, 1)
	go func() {
		defer pw.Close()
		err := execInPodStream(ctx, clientset, config, namespace, podName, containerName,
			[]string{"tar", "-c", "-C", searchPath, "."}, pw)
		errChan <- err
	}()

	// Stream the tar data to the client
	buffer := make([]byte, 64*1024) // 64KB chunks
	for {
		n, err := pr.Read(buffer)
		if n > 0 {
			if serr := stream.Send(&CaptureChunk{Data: buffer[:n]}); serr != nil {
				return serr
			}
		}
		if err != nil {
			if err == io.EOF {
				break
			}
			return status.Errorf(codes.Internal, "failed to read tar stream: %v", err)
		}
	}

	// Check if tar command succeeded
	if err := <-errChan; err != nil {
		return status.Errorf(codes.Internal, "tar command failed: %v", err)
	}

	return nil
}
