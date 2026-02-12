// Scenario Builder JavaScript

let currentScenarioType = 'monopod';
let kvPairCount = 0;
let ruleCount = 0;

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    initScenarioBuilder();
});

function initScenarioBuilder() {
    // Scenario type switching
    document.querySelectorAll('.scenario-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.scenario-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            currentScenarioType = this.dataset.type;
            showScenarioPanel(currentScenarioType);
        });
    });

    // Initialize monopod panel
    showScenarioPanel('monopod');

    // Form submission
    document.getElementById('scenarioForm').addEventListener('submit', handleFormSubmit);

    // Add KV pair
    document.getElementById('add-kv-btn').addEventListener('click', addKVPair);

    // Add port
    document.getElementById('add-port-btn').addEventListener('click', addPort);

    // Add rule
    document.getElementById('add-rule-btn').addEventListener('click', addRule);

    // Add multipod port
    document.getElementById('add-multipod-port-btn').addEventListener('click', addMultipodPort);

    // Add container
    document.getElementById('add-container-btn').addEventListener('click', addContainer);
}

function showScenarioPanel(type) {
    document.querySelectorAll('.scenario-panel').forEach(panel => {
        panel.classList.remove('active');
    });
    document.getElementById(type + '-panel').classList.add('active');
}

async function handleFormSubmit(e) {
    e.preventDefault();
    
    const submitBtn = document.getElementById('submit-btn');
    const loading = document.getElementById('loading');
    const resultCard = document.getElementById('result-card');
    const errorCard = document.getElementById('error-card');
    
    submitBtn.disabled = true;
    loading.classList.add('show');
    errorCard.classList.remove('show');
    resultCard.classList.remove('show');
    
    try {
        const formData = collectFormData();
        
        // Check if we should push to registry or just download
        const pushToRegistry = document.getElementById('push-to-registry')?.checked;
        
        if (pushToRegistry) {
            // Build and push to registry
            await buildAndPushScenario(formData);
        } else {
            // Download ZIP
            await downloadScenarioZip(formData);
        }
        
    } catch (error) {
        document.getElementById('error-message').textContent = error.message;
        errorCard.classList.add('show');
    } finally {
        submitBtn.disabled = false;
        loading.classList.remove('show');
    }
}

async function downloadScenarioZip(formData) {
    const response = await fetch('/api/create-scenario', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
    });
    
    if (response.ok) {
        // Download the ZIP file
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${formData.identity}-scenario.zip`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
        // Show success
        document.getElementById('result-message').textContent = 'Scenario downloaded successfully!';
        document.getElementById('cli-command').textContent = 
            `cd ${formData.identity} && pulumi up`;
        document.getElementById('result-card').classList.add('show');
    } else {
        const error = await response.json();
        throw new Error(error.error || 'Failed to create scenario');
    }
}

async function buildAndPushScenario(formData) {
    const response = await fetch('/api/build-and-push-scenario', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
    });
    
    const result = await response.json();
    
    if (response.ok && result.success) {
        document.getElementById('scenario-ref').textContent = result.scenario_ref;
        document.getElementById('cli-command').textContent = 
            `chall-manager-cli challenge create \\\n    --id ${formData.identity} \\\n    --scenario ${result.scenario_ref} \\\n    --image-pull-secrets ${formData.image_pull_secrets || ''}`;
        document.getElementById('result-card').classList.add('show');
        
        // Show additional instructions
        if (result.instructions) {
            console.log('Push instructions:', result.instructions);
        }
    } else {
        throw new Error(result.error || 'Unknown error');
    }
}

async function createChallengeFromScenario(formData) {
    const response = await fetch('/api/create-challenge-from-scenario', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            identity: formData.identity,
            scenario_ref: formData.scenario_ref,
            image_pull_secrets: formData.image_pull_secrets,
        }),
    });
    
    const result = await response.json();
    
    if (response.ok && result.success) {
        document.getElementById('scenario-ref').textContent = result.scenario_ref;
        document.getElementById('cli-command').textContent = result.cli_command;
        document.getElementById('result-card').classList.add('show');
    } else {
        throw new Error(result.error || 'Failed to create challenge');
    }
}

function collectFormData() {
    const data = {
        scenario_type: currentScenarioType,
        identity: document.getElementById('identity').value,
        challenge_id: document.getElementById('challenge_id').value,
        hostname: document.getElementById('hostname').value,
        label: document.getElementById('label').value,
        registry_url: document.getElementById('registry_url').value,
        registry_username: document.getElementById('registry_username').value,
        registry_password: document.getElementById('registry_password').value,
        tag: document.getElementById('tag').value,
        image_pull_secrets: document.getElementById('image_pull_secrets').value,
        packet_capture_pvc: document.getElementById('packet_capture_pvc').value,
        additional_config: document.getElementById('additional_config').value,
    };

    if (currentScenarioType === 'monopod') {
        data.container = collectContainerData();
    } else if (currentScenarioType === 'multipod') {
        data.containers = collectContainersData();
        data.rules = collectRulesData();
    } else if (currentScenarioType === 'kompose') {
        data.compose_yaml = document.getElementById('compose_yaml').value;
        data.service_ports = collectServicePortsData();
        data.packet_capture = collectPacketCaptureData();
    }

    return data;
}

function collectContainerData() {
    const containerData = {
        name: document.getElementById('container_name').value || 'main',
        image: document.getElementById('image').value,
        ports: collectPortsData(),
        envs: document.getElementById('envs').value,
        limit_cpu: document.getElementById('limit_cpu').value,
        limit_memory: document.getElementById('limit_memory').value,
        packet_capture: document.getElementById('packet_capture').checked,
    };
    return containerData;
}

function collectContainersData() {
    const containers = [];
    document.querySelectorAll('#containers-container .container-item').forEach(item => {
        containers.push({
            name: item.querySelector('.container-name').value,
            image: item.querySelector('.container-image').value,
            ports: collectMultipodPortsData(item),
            envs: item.querySelector('.container-envs').value,
            limit_cpu: item.querySelector('.container-cpu').value,
            limit_memory: item.querySelector('.container-memory').value,
            packet_capture: item.querySelector('.container-pcap').checked,
        });
    });
    return containers;
}

function collectPortsData() {
    const ports = [];
    document.querySelectorAll('#ports-container .port-item').forEach(item => {
        ports.push({
            port: parseInt(item.querySelector('.port-number').value),
            protocol: item.querySelector('.port-protocol').value,
            expose_type: item.querySelector('.port-expose').value,
        });
    });
    return ports;
}

function collectMultipodPortsData(containerItem) {
    const ports = [];
    containerItem.querySelectorAll('.multipod-port-item').forEach(item => {
        ports.push({
            port: parseInt(item.querySelector('.multipod-port-number').value),
            protocol: item.querySelector('.multipod-port-protocol').value,
            expose_type: item.querySelector('.multipod-port-expose').value,
        });
    });
    return ports;
}

function collectRulesData() {
    const rules = [];
    document.querySelectorAll('#rules-container .rule-item').forEach(item => {
        rules.push({
            from_container: item.querySelector('.rule-from').value,
            to_container: item.querySelector('.rule-to').value,
            ports: item.querySelector('.rule-ports').value,
            protocol: item.querySelector('.rule-protocol').value,
        });
    });
    return rules;
}

function collectServicePortsData() {
    const servicePorts = {};
    document.querySelectorAll('#service-ports-container .service-port-item').forEach(item => {
        const serviceName = item.querySelector('.service-name').value;
        const ports = [];
        item.querySelectorAll('.port-entry').forEach(portEntry => {
            ports.push({
                port: parseInt(portEntry.querySelector('.port-number').value),
                protocol: portEntry.querySelector('.port-protocol').value,
                expose_type: portEntry.querySelector('.port-expose').value,
            });
        });
        servicePorts[serviceName] = ports;
    });
    return servicePorts;
}

function collectPacketCaptureData() {
    const packetCapture = {};
    document.querySelectorAll('#service-ports-container .service-port-item').forEach(item => {
        const serviceName = item.querySelector('.service-name').value;
        const enabled = item.querySelector('.pcap-enabled').checked;
        packetCapture[serviceName] = enabled;
    });
    return packetCapture;
}

function addKVPair() {
    kvPairCount++;
    const container = document.getElementById('kv-pairs-container');
    const kvItem = document.createElement('div');
    kvItem.className = 'kv-item';
    kvItem.id = `kv-${kvPairCount}`;
    kvItem.innerHTML = `
        <input type="text" placeholder="Key" class="kv-key">
        <input type="text" placeholder="Value" class="kv-value">
        <button type="button" class="btn btn-danger" onclick="removeKVPair(${kvPairCount})">Remove</button>
    `;
    container.appendChild(kvItem);
}

function removeKVPair(id) {
    const item = document.getElementById(`kv-${id}`);
    if (item) item.remove();
}

function addPort() {
    const container = document.getElementById('ports-container');
    const portItem = document.createElement('div');
    portItem.className = 'port-item';
    portItem.innerHTML = `
        <input type="number" placeholder="Port" class="port-number" min="1" max="65535">
        <select class="port-protocol">
            <option value="TCP">TCP</option>
            <option value="UDP">UDP</option>
        </select>
        <select class="port-expose">
            <option value="internal">Internal</option>
            <option value="NodePort">NodePort</option>
            <option value="LoadBalancer">LoadBalancer</option>
            <option value="ingress">Ingress</option>
        </select>
        <button type="button" class="btn btn-danger" onclick="this.parentElement.remove()">Remove</button>
    `;
    container.appendChild(portItem);
}

function addMultipodPort(containerId) {
    const container = document.getElementById(containerId).querySelector('.multipod-ports-container');
    const portItem = document.createElement('div');
    portItem.className = 'multipod-port-item';
    portItem.innerHTML = `
        <input type="number" placeholder="Port" class="multipod-port-number" min="1" max="65535">
        <select class="multipod-port-protocol">
            <option value="TCP">TCP</option>
            <option value="UDP">UDP</option>
        </select>
        <select class="multipod-port-expose">
            <option value="internal">Internal</option>
            <option value="NodePort">NodePort</option>
            <option value="LoadBalancer">LoadBalancer</option>
            <option value="ingress">Ingress</option>
        </select>
        <button type="button" class="btn btn-danger" onclick="this.parentElement.remove()">Remove</button>
    `;
    container.appendChild(portItem);
}

function addContainer() {
    const containerId = 'container-' + Date.now();
    const container = document.getElementById('containers-container');
    const containerItem = document.createElement('div');
    containerItem.className = 'container-item';
    containerItem.id = containerId;
    containerItem.innerHTML = `
        <h4>Container</h4>
        <div class="form-group">
            <label>Name</label>
            <input type="text" class="container-name" placeholder="container-name">
        </div>
        <div class="form-group">
            <label>Image</label>
            <input type="text" class="container-image" placeholder="nginx:latest">
        </div>
        <div class="form-group">
            <label>Ports</label>
            <div class="multipod-ports-container"></div>
            <button type="button" class="btn btn-secondary" onclick="addMultipodPort('${containerId}')">Add Port</button>
        </div>
        <div class="form-group">
            <label>Environment Variables (KEY=VALUE, one per line)</label>
            <textarea class="container-envs" rows="3" placeholder="DEBUG=true"></textarea>
        </div>
        <div class="form-group">
            <label>Resource Limits</label>
            <input type="text" class="container-cpu" placeholder="500m">
            <input type="text" class="container-memory" placeholder="512Mi">
        </div>
        <div class="form-group">
            <label>
                <input type="checkbox" class="container-pcap"> Enable Packet Capture
            </label>
        </div>
        <button type="button" class="btn btn-danger" onclick="this.parentElement.remove()">Remove Container</button>
    `;
    container.appendChild(containerItem);
}

function addRule() {
    const container = document.getElementById('rules-container');
    const ruleItem = document.createElement('div');
    ruleItem.className = 'rule-item';
    ruleItem.innerHTML = `
        <input type="text" placeholder="From Container" class="rule-from">
        <input type="text" placeholder="To Container" class="rule-to">
        <input type="text" placeholder="Ports (comma-separated)" class="rule-ports">
        <select class="rule-protocol">
            <option value="TCP">TCP</option>
            <option value="UDP">UDP</option>
        </select>
        <button type="button" class="btn btn-danger" onclick="this.parentElement.remove()">Remove</button>
    `;
    container.appendChild(ruleItem);
}

// Copy to clipboard function
function copyToClipboard(elementId) {
    const element = document.getElementById(elementId);
    const text = element.textContent;
    navigator.clipboard.writeText(text).then(() => {
        alert('Copied to clipboard!');
    });
}
