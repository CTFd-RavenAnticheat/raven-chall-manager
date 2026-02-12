        let currentScenarioType = 'monopod';
        let multipodContainerCount = 0;
        let ruleCount = 0;

        // Scenario type selector
        document.querySelectorAll('.type-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.type-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                
                currentScenarioType = btn.dataset.type;
                
                // Show/hide scenario-specific sections
                document.querySelectorAll('.scenario-specific').forEach(section => {
                    section.classList.remove('active');
                });
                document.getElementById(currentScenarioType + '-section').classList.add('active');
            });
        });

        // Update button text based on push-to-registry checkbox
        const pushCheckbox = document.getElementById('push-to-registry');
        const submitBtn = document.getElementById('submit-btn');
        const loadingText = document.getElementById('loading-text');
        
        function updateSubmitButton() {
            if (pushCheckbox.checked) {
                submitBtn.textContent = '🚀 Create & Push Scenario';
                loadingText.textContent = 'Building and pushing scenario...';
            } else {
                submitBtn.textContent = '📦 Create & Download ZIP';
                loadingText.textContent = 'Building scenario...';
            }
        }
        
        pushCheckbox.addEventListener('change', updateSubmitButton);
        updateSubmitButton();  // Set initial state

        // Add port to container
        function addPort(btn) {
            const portsList = btn.previousElementSibling;
            const newPort = document.createElement('div');
            newPort.className = 'port-row';
            newPort.innerHTML = `
                <input type="number" class="port-number" placeholder="Port" min="1" max="65535">
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
                <button type="button" class="remove-port-btn" onclick="removePort(this)">✕</button>
            `;
            portsList.appendChild(newPort);
        }

        // Remove port
        function removePort(btn) {
            btn.parentElement.remove();
        }

        // Add Multipod container
        function addMultipodContainer() {
            multipodContainerCount++;
            const container = document.createElement('div');
            container.className = 'container-card';
            container.dataset.containerIdx = multipodContainerCount;
            container.innerHTML = `
                <button type="button" class="remove-btn" onclick="this.parentElement.remove()">Remove</button>
                <h4>Container ${multipodContainerCount}</h4>
                <div class="form-row">
                    <div class="form-group">
                        <label>Name *</label>
                        <input type="text" class="container-name" required placeholder="e.g., web">
                    </div>
                    <div class="form-group">
                        <label>Image *</label>
                        <input type="text" class="container-image" required placeholder="nginx:latest">
                    </div>
                </div>
                <div class="form-group">
                    <label>Ports</label>
                    <div class="ports-list">
                        <div class="port-row">
                            <input type="number" class="port-number" placeholder="Port" min="1" max="65535" value="80">
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
                            <button type="button" class="remove-port-btn" onclick="removePort(this)">✕</button>
                        </div>
                    </div>
                    <button type="button" class="add-btn" onclick="addPort(this)">+ Add Port</button>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Environment Variables</label>
                        <textarea class="container-envs" rows="3" placeholder="KEY=value&#10;FLAG=CTF{...}"></textarea>
                    </div>
                    <div class="form-group">
                        <label>Files (path=content format)</label>
                        <textarea class="container-files" rows="3" placeholder="/app/config.txt=Hello World&#10;/etc/flag.txt=CTF{...}"></textarea>
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>CPU Limit</label>
                        <input type="text" class="container-cpu" placeholder="e.g., 500m" value="500m">
                    </div>
                    <div class="form-group">
                        <label>Memory Limit</label>
                        <input type="text" class="container-memory" placeholder="e.g., 256Mi" value="256Mi">
                    </div>
                </div>
                <div class="form-group checkbox-group">
                    <input type="checkbox" class="container-pcap" id="pcap-${multipodContainerCount}">
                    <label for="pcap-${multipodContainerCount}">Enable Packet Capture</label>
                </div>
            `;
            document.getElementById('multipod-containers').appendChild(container);
        }

        // Add network rule
        function addRule() {
            ruleCount++;
            const rule = document.createElement('div');
            rule.className = 'container-card';
            rule.style.background = '#fff3cd';
            rule.innerHTML = `
                <button type="button" class="remove-btn" onclick="this.parentElement.remove()">Remove</button>
                <h4>Rule ${ruleCount}</h4>
                <div class="form-row">
                    <div class="form-group">
                        <label>From Container</label>
                        <input type="text" class="rule-from" required placeholder="container name">
                    </div>
                    <div class="form-group">
                        <label>To Container</label>
                        <input type="text" class="rule-to" required placeholder="container name">
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Ports (comma-separated)</label>
                        <input type="text" class="rule-ports" required placeholder="8080, 5432">
                    </div>
                    <div class="form-group">
                        <label>Protocol</label>
                        <select class="rule-protocol">
                            <option value="TCP">TCP</option>
                            <option value="UDP">UDP</option>
                        </select>
                    </div>
                </div>
            `;
            document.getElementById('multipod-rules').appendChild(rule);
        }

        // Form submission
        document.getElementById('scenario-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const submitBtn = document.getElementById('submit-btn');
            const loading = document.getElementById('loading');
            const errorCard = document.getElementById('error-card');
            const resultCard = document.getElementById('result-card');
            
            submitBtn.disabled = true;
            loading.classList.add('show');
            errorCard.classList.remove('show');
            resultCard.classList.remove('show');
            
            try {
                const formData = collectFormData();
                const pushToRegistry = document.getElementById('push-to-registry')?.checked || false;
                
                if (pushToRegistry) {
                    // Push to registry
                    await pushScenarioToRegistry(formData);
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
        });
        
        // Push scenario to registry
        async function pushScenarioToRegistry(formData) {
            const response = await fetch('/api/build-and-push-scenario', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData),
            });
            
            const result = await response.json();
            
            if (response.ok && result.success) {
                document.getElementById('result-message').textContent = 'Your scenario has been built and pushed to the registry:';
                document.getElementById('scenario-ref').textContent = result.scenario_ref;
                document.getElementById('cli-heading').textContent = 'Use with chall-manager:';
                document.getElementById('cli-command').textContent = 
                    `chall-manager-cli challenge create \\\n    --id ${formData.identity} \\\n    --scenario ${result.scenario_ref} \\\n    --image-pull-secrets ${formData.image_pull_secrets || ''}`;
                document.getElementById('result-card').classList.add('show');
            } else {
                throw new Error(result.error || 'Failed to push scenario');
            }
        }
        
        // Download scenario ZIP
        async function downloadScenarioZip(formData) {
            const response = await fetch('/api/create-scenario', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
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
                
                // Show success message
                document.getElementById('result-message').textContent = 'Your scenario has been built and downloaded:';
                document.getElementById('scenario-ref').textContent = `${formData.identity}-scenario.zip`;
                document.getElementById('cli-heading').textContent = 'Deploy locally:';
                document.getElementById('cli-command').textContent = 
                    `# Extract and deploy locally:\nunzip ${formData.identity}-scenario.zip\ncd ${formData.identity}\npulumi up`;
                document.getElementById('result-card').classList.add('show');
            } else {
                const result = await response.json();
                throw new Error(result.error || 'Failed to create scenario');
            }
        }

        // Collect form data based on scenario type
        function collectFormData() {
            const data = {
                scenario_type: currentScenarioType,
                identity: document.getElementById('identity').value,
                hostname: document.getElementById('hostname').value,
                connection_format: document.getElementById('connection_format').value || 'nc %s',
                label: document.getElementById('label').value,
                tag: document.getElementById('tag').value || 'latest',
                registry_url: document.getElementById('registry_url').value,
                image_pull_secrets: document.getElementById('image_pull_secrets').value,
                packet_capture_pvc: document.getElementById('packet_capture_pvc').value || 'pcap-core',
                ingress_namespace: document.getElementById('ingress_namespace').value || 'networking',
                ingress_labels: document.getElementById('ingress_labels').value,
                ingress_annotations: document.getElementById('ingress_annotations').value,
            };

            if (currentScenarioType === 'monopod') {
                data.container = collectContainerData(
                    document.querySelector('#monopod-containers .container-card')
                );
            } else if (currentScenarioType === 'multipod') {
                data.containers = [];
                document.querySelectorAll('#multipod-containers .container-card').forEach(card => {
                    data.containers.push(collectContainerData(card));
                });
                
                data.rules = [];
                document.querySelectorAll('#multipod-rules .container-card').forEach(card => {
                    data.rules.push({
                        from_container: card.querySelector('.rule-from').value,
                        to_container: card.querySelector('.rule-to').value,
                        ports: card.querySelector('.rule-ports').value,
                        protocol: card.querySelector('.rule-protocol').value,
                    });
                });
            } else if (currentScenarioType === 'kompose') {
                data.compose_yaml = document.getElementById('compose-yaml').value;
            }

            return data;
        }

        // Collect container data from card
        function collectContainerData(card) {
            const ports = [];
            card.querySelectorAll('.port-row').forEach(row => {
                const portNumber = row.querySelector('.port-number').value;
                if (portNumber) {
                    ports.push({
                        port: parseInt(portNumber),
                        protocol: row.querySelector('.port-protocol').value,
                        expose_type: row.querySelector('.port-expose').value,
                    });
                }
            });

            return {
                name: card.querySelector('.container-name').value,
                image: card.querySelector('.container-image').value,
                ports: ports,
                envs: card.querySelector('.container-envs').value,
                files: card.querySelector('.container-files')?.value || '',
                limit_cpu: card.querySelector('.container-cpu').value || '500m',
                limit_memory: card.querySelector('.container-memory').value || '256Mi',
                packet_capture: card.querySelector('.container-pcap').checked,
            };
        }

        // Copy scenario reference
        function copyScenarioRef() {
            const ref = document.getElementById('scenario-ref').textContent;
            navigator.clipboard.writeText(ref).then(() => {
                alert('Copied to clipboard!');
            });
        }

        // Copy CLI command
        function copyCliCommand() {
            const cmd = document.getElementById('cli-command').textContent;
            navigator.clipboard.writeText(cmd).then(() => {
                alert('Copied to clipboard!');
            });
        }
