# 🔐 Secret Manager - New Feature!

The Chall-Manager Web UI now includes a **Secret Manager** for creating and managing Kubernetes secrets dynamically!

## Features

### 🎯 Three Secret Types

1. **Docker Registry Secrets**
   - Store credentials for private registries (GitLab, DockerHub, etc.)
   - Test connection before creating
   - Support for username/password or tokens

2. **Generic Secrets**
   - Store key-value pairs
   - Perfect for flags, API keys, configuration
   - Add/remove keys dynamically

3. **TLS Secrets**
   - Store certificates and private keys
   - For HTTPS ingress
   - PEM format support

### 🚀 Quick Start

#### Access the Secret Manager

1. Start the web UI:
```bash
./start.sh
```

2. Navigate to **http://localhost:5000/secrets**

3. Or click "Secret Manager" in the navigation bar

#### Create GitLab Registry Secret

1. Click "🐳 Docker Registry"
2. Fill in:
   - **Name**: `gitlab-registry`
   - **Server**: `registry.gitlab.com`
   - **Username**: `BitravenS1`
   - **Password**: `glpat-JfWuSZHB7TRN6hrnxzGzuG86MQp1OmkwaHYxCw.01.120vwbovh`
3. Click "🧪 Test Connection" to verify
4. Click "🔐 Create Registry Secret"

#### Use in Scenario Builder

After creating the secret, go back to the Scenario Builder and:
1. Add `gitlab-registry` to "Image Pull Secrets" field
2. Use private registry images in your containers

## API Endpoints

### List Secrets
```bash
GET /api/secrets/list
```

### Create Docker Registry Secret
```bash
POST /api/secrets/create/docker-registry
Content-Type: application/json

{
  "name": "gitlab-registry",
  "namespace": "chall-manager",
  "server": "registry.gitlab.com",
  "username": "BitravenS1",
  "password": "glpat-...",
  "email": "optional@example.com"
}
```

### Create Generic Secret
```bash
POST /api/secrets/create/generic
Content-Type: application/json

{
  "name": "challenge-flags",
  "namespace": "chall-manager",
  "data": {
    "FLAG": "CTF{example_flag}",
    "API_KEY": "secret123"
  }
}
```

### Create TLS Secret
```bash
POST /api/secrets/create/tls
Content-Type: application/json

{
  "name": "challenge-tls",
  "namespace": "chall-manager",
  "cert": "-----BEGIN CERTIFICATE-----...",
  "key": "-----BEGIN PRIVATE KEY-----..."
}
```

### Test Registry Connection
```bash
POST /api/secrets/test-registry
Content-Type: application/json

{
  "server": "registry.gitlab.com",
  "username": "BitravenS1",
  "password": "glpat-..."
}
```

### Delete Secret
```bash
DELETE /api/secrets/delete/{secret_name}?namespace=chall-manager
```

## Integration with Chall-Manager

Once you've created secrets, use them when creating challenges:

### Via Web UI
1. Go to Scenario Builder
2. In "Advanced Options", add your secret name to "Image Pull Secrets"
3. Use private registry images

### Via CLI
```bash
chall-manager-cli challenge create \
    --id my-private-challenge \
    --scenario registry.gitlab.com/group/challenge:latest \
    --image-pull-secrets gitlab-registry
```

### Via API
```bash
curl -X POST http://chall-manager:8080/api/v1/challenge \
  -H "Content-Type: application/json" \
  -d '{
    "id": "my-challenge",
    "scenario": "registry.gitlab.com/group/challenge:latest",
    "image_pull_secrets": ["gitlab-registry"]
  }'
```

## UI Features

- 🎨 **Modern Interface**: Beautiful, responsive design
- 📋 **Quick Actions**: Click cards to select secret type
- 🧪 **Test Connections**: Verify registry credentials work
- 📊 **Secret Listing**: View all secrets with usage info
- 🗑️ **Easy Deletion**: Delete secrets with confirmation
- 📋 **YAML Export**: Copy secret manifests for manual use
- 🔄 **Dynamic Forms**: Add/remove key-value pairs

## Security Notes

- Secrets are created in the `chall-manager` namespace by default
- Passwords/tokens are never displayed after creation
- All secret data is base64 encoded (Kubernetes standard)
- Delete unused secrets to maintain security

## Example: Complete GitLab Workflow

```bash
# 1. Start the web UI
./start.sh

# 2. Open http://localhost:5000/secrets

# 3. Create GitLab registry secret:
#    - Name: gitlab-registry
#    - Server: registry.gitlab.com
#    - Username: BitravenS1
#    - Password: glpat-JfWuSZHB7TRN6hrnxzGzuG86MQp1OmkwaHYxCw.01.120vwbovh

# 4. Go to Scenario Builder

# 5. Create a challenge with private image:
#    - Container Image: registry.gitlab.com/bitraven/challenges/web:latest
#    - Image Pull Secrets: gitlab-registry

# 6. Deploy and enjoy!
```