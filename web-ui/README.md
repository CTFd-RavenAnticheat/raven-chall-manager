# Chall-Manager Web UI

A beautiful Flask web application for creating and deploying CTF challenge scenarios using chall-manager.

## Features

- 🎨 Modern, responsive UI with smooth animations
- 📦 Support for all three scenario types:
  - **Monopod**: Single container challenges
  - **Multipod**: Multi-container challenges with network policies
  - **Docker Compose**: Import existing docker-compose.yaml files
- 🔐 Private registry authentication support
- 📊 Packet capture configuration
- 🔧 Advanced options (resource limits, environment variables, etc.)
- ✨ Real-time form validation and dynamic UI
- 📋 One-click copying of scenario references and CLI commands

## Screenshots

The web interface provides an intuitive form-based approach to creating scenarios:

1. **Choose Scenario Type**: Select between Monopod, Multipod, or Docker Compose
2. **Basic Configuration**: Set identity, hostname, and labels
3. **Container Configuration**: Define containers, ports, and resources
4. **Registry Settings**: Configure private registry authentication
5. **Advanced Options**: Set image pull secrets, packet capture, and more

## Installation

### Prerequisites

- Python 3.8+
- chall-manager Python SDK (in `../sdk/python/`)

### Setup

```bash
# Navigate to web-ui directory
cd web-ui

# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Start the Development Server

```bash
python app.py
```

The web UI will be available at: **http://localhost:5000**

### Environment Variables

Configure the following environment variables (optional):

```bash
export REGISTRY_URL="registry.example.com:5000"
export REGISTRY_USERNAME="your-username"
export REGISTRY_PASSWORD="your-password"
export SECRET_KEY="your-secret-key-for-flask"
```

Or create a `.env` file:

```
REGISTRY_URL=registry.example.com:5000
REGISTRY_USERNAME=your-username
REGISTRY_PASSWORD=your-password
SECRET_KEY=dev-secret-key-change-in-production
```

### Using the Web UI

1. **Select Scenario Type**
   - **Monopod**: Single container (e.g., simple web challenge)
   - **Multipod**: Multiple containers with networking (e.g., web + database)
   - **Docker Compose**: Import existing docker-compose.yaml

2. **Fill Basic Configuration**
   - Challenge Identity (required)
   - Challenge ID (optional, defaults to identity)
   - Hostname (for ingress)
   - Label (for categorization)

3. **Configure Container(s)**
   - Container name and image
   - Ports (with exposure type: Internal, NodePort, LoadBalancer, Ingress)
   - Environment variables
   - Resource limits (CPU/Memory)
   - Packet capture (if needed)

4. **For Multipod**: Add network rules between containers

5. **Configure Registry**
   - Registry URL
   - Authentication credentials (optional)
   - Tag (defaults to "latest")

6. **Set Advanced Options**
   - Image pull secrets for private registries
   - Packet capture PVC
   - Additional configuration

7. **Click "Create & Push Scenario"**

8. **Copy the Result**
   - Scenario reference URL
   - Ready-to-use chall-manager CLI command

## Example Workflow

### Creating a Web Challenge

1. Select **Monopod**
2. Set identity: `web-challenge-1`
3. Set hostname: `ctf.example.com`
4. Configure container:
   - Name: `web`
   - Image: `nginx:latest`
   - Port: `80` with **Ingress** exposure
   - Environment: `FLAG=CTF{example_flag}`
5. Set registry URL
6. Click create

### Creating a Multi-Tier Application

1. Select **Multipod**
2. Set identity: `multi-tier-app`
3. Add containers:
   - `web`: nginx on port 80 (Ingress)
   - `api`: python app on port 8080
   - `db`: postgres on port 5432
4. Add rules:
   - `web` → `api` on port 8080
   - `api` → `db` on port 5432
5. Create scenario

### Importing Docker Compose

1. Select **Docker Compose**
2. Paste your `docker-compose.yaml`
3. Configure service ports
4. Set packet capture options
5. Create scenario

## API Endpoints

### POST /api/create-scenario

Creates a scenario and pushes it to the registry.

**Request Body:**
```json
{
  "scenario_type": "monopod",
  "identity": "web-challenge",
  "hostname": "ctf.example.com",
  "registry_url": "registry.example.com:5000",
  "container": {
    "name": "web",
    "image": "nginx:latest",
    "ports": [
      {"port": 80, "protocol": "TCP", "expose_type": "ingress"}
    ],
    "envs": "FLAG=CTF{example}",
    "packet_capture": false
  }
}
```

**Response:**
```json
{
  "success": true,
  "scenario_ref": "registry.example.com:5000/scenarios/web-challenge:latest",
  "message": "Scenario successfully created and pushed..."
}
```

## Architecture

### Frontend
- Pure HTML/CSS/JavaScript (no frameworks)
- Responsive design with CSS Grid and Flexbox
- Dynamic form handling with vanilla JS
- Smooth animations and transitions

### Backend
- Flask web framework
- WTForms for form validation
- chall-manager Python SDK for scenario generation
- JSON API for AJAX requests

### Scenario Generation Flow

1. User fills form and submits
2. Frontend collects form data as JSON
3. POST to `/api/create-scenario`
4. Backend validates and builds scenario using SDK
5. Generates Pulumi Python code
6. Pushes to OCI registry
7. Returns scenario reference
8. Frontend displays result with copy buttons

## Customization

### Adding New Form Fields

1. Add field to HTML template in `templates/index.html`
2. Add field handling in JavaScript `collectFormData()` function
3. Add field processing in Flask route `create_scenario()`
4. Update SDK builder calls

### Styling

The UI uses CSS custom properties for theming. Edit the `<style>` section in `templates/index.html` to customize:

```css
:root {
  --primary-color: #667eea;
  --secondary-color: #764ba2;
  --success-color: #11998e;
  --error-color: #ff416c;
}
```

## Production Deployment

### Using Gunicorn

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### Using Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
```

### Using Docker Compose

```yaml
version: '3.8'
services:
  web-ui:
    build: .
    ports:
      - "5000:5000"
    environment:
      - REGISTRY_URL=registry.example.com:5000
      - REGISTRY_USERNAME=${REGISTRY_USERNAME}
      - REGISTRY_PASSWORD=${REGISTRY_PASSWORD}
      - SECRET_KEY=${SECRET_KEY}
```

## Troubleshooting

### Scenario push fails

- Check registry URL is accessible
- Verify registry credentials
- Ensure registry supports OCI artifacts

### Container fails to start

- Check image name is correct
- Verify ports don't conflict
- Check resource limits are reasonable

### Network issues

- For Multipod: ensure network rules are correct
- Check that referenced containers exist
- Verify port protocols match

## Development

### Running in Debug Mode

```python
# In app.py
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
```

### Adding New Scenario Types

1. Create new form section in HTML
2. Add JavaScript handling
3. Implement builder function in `app.py`
4. Add API endpoint handling

## Integration with Chall-Manager

Once a scenario is created:

```bash
# Copy the CLI command from the web UI
chall-manager-cli challenge create \
    --id web-challenge-1 \
    --scenario registry.example.com:5000/scenarios/web-challenge-1:latest \
    --image-pull-secrets gitlab-registry
```

## License

Apache License 2.0 - Same as chall-manager