// Boondock Monitor - Frontend Application
let streams = [];
let devices = [];
let outputChannels = [];
let noiseProfiles = [];
let noisePresets = [];
let statusInterval = null;
let lastChannelsJson = '';
let dropdownInteractionActive = false;

// Initialize on load
document.addEventListener('DOMContentLoaded', async () => {
    await loadDevices();
    await loadStreams();
    await loadNoiseProfiles();
    await loadNoisePresets();
    await loadOutputChannels(true);
    
    // Track dropdown interactions to prevent refresh during interaction
    document.addEventListener('mousedown', (e) => {
        if (e.target.tagName === 'SELECT') {
            dropdownInteractionActive = true;
        }
    });
    
    document.addEventListener('mouseup', (e) => {
        if (e.target.tagName === 'SELECT') {
            setTimeout(() => {
                dropdownInteractionActive = false;
            }, 100);
        }
    });
    
    document.addEventListener('focus', (e) => {
        if (e.target.tagName === 'SELECT') {
            dropdownInteractionActive = true;
        }
    }, true);
    
    document.addEventListener('blur', (e) => {
        if (e.target.tagName === 'SELECT') {
            setTimeout(() => {
                dropdownInteractionActive = false;
            }, 100);
        }
    }, true);
    
    // Poll status every second
    statusInterval = setInterval(() => {
        loadOutputChannels(false);
    }, 1000);
});

// ============== API Calls ==============

async function api(endpoint, method = 'GET', data = null) {
    const options = {
        method,
        headers: { 'Content-Type': 'application/json' }
    };
    if (data) options.body = JSON.stringify(data);
    
    const response = await fetch(`/api${endpoint}`, options);
    return response.json();
}

// ============== Devices ==============

async function loadDevices() {
    devices = await api('/devices');
    renderDevices();
    populateDeviceSelects();
}

function renderDevices() {
    const table = document.getElementById('devicesTable');
    
    if (devices.length === 0) {
        table.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No USB audio devices found</td></tr>';
        return;
    }
    
    table.innerHTML = devices.map(dev => `
        <tr>
            <td><span class="badge bg-secondary">${dev.id}</span></td>
            <td>${escapeHtml(dev.name)}</td>
            <td>${dev.channels}</td>
            <td>${dev.sample_rate} Hz</td>
            <td>
                <button class="btn btn-sm btn-outline-info" onclick="testDevice(${dev.id})">
                    <i class="bi bi-volume-up"></i> Test
                </button>
            </td>
        </tr>
    `).join('');
}

function populateDeviceSelects() {
    const select = document.getElementById('outputChannelDevice');
    if (select) {
        const usedDeviceIds = outputChannels.map(ch => ch.device_id);
        const editingChannelId = document.getElementById('outputChannelId')?.value;
        const editingChannel = editingChannelId ? outputChannels.find(c => c.id == editingChannelId) : null;
        
        select.innerHTML = '<option value="">-- Select Device --</option>' +
            devices.map(d => {
                const isUsed = usedDeviceIds.includes(d.id) && (!editingChannel || editingChannel.device_id !== d.id);
                return `<option value="${d.id}" ${isUsed ? 'disabled' : ''}>${escapeHtml(d.name)}${isUsed ? ' (in use)' : ''}</option>`;
            }).join('');
    }
}

async function testDevice(deviceId) {
    await api('/devices/test', 'POST', { device_id: deviceId });
}

function refreshDevices() {
    loadDevices();
}

// ============== Noise Profiles ==============

async function loadNoiseProfiles() {
    noiseProfiles = await api('/noise-profiles');
    renderNoiseProfilesList();
}

function renderNoiseProfilesList() {
    const container = document.getElementById('noiseProfilesList');
    if (!container) return;
    
    if (noiseProfiles.length === 0) {
        container.innerHTML = '<p class="text-muted text-center">No noise profiles uploaded yet.</p>';
        return;
    }
    
    container.innerHTML = noiseProfiles.map(p => `
        <div class="config-item d-flex justify-content-between align-items-center">
            <div>
                <strong>${escapeHtml(p.name)}</strong>
                <div class="small text-muted">${escapeHtml(p.original_filename)}</div>
            </div>
            <button class="btn btn-sm btn-outline-danger" onclick="deleteNoiseProfile(${p.id})">
                <i class="bi bi-trash"></i>
            </button>
        </div>
    `).join('');
}

async function uploadNoiseProfile() {
    const name = document.getElementById('noiseProfileName').value.trim();
    const fileInput = document.getElementById('noiseFile');
    
    if (!name || !fileInput.files.length) {
        alert('Please enter a name and select a file');
        return;
    }
    
    const formData = new FormData();
    formData.append('name', name);
    formData.append('file', fileInput.files[0]);
    
    await fetch('/api/noise-profiles', { method: 'POST', body: formData });
    
    document.getElementById('noiseProfileName').value = '';
    fileInput.value = '';
    await loadNoiseProfiles();
}

async function deleteNoiseProfile(id) {
    if (!confirm('Delete this noise profile?')) return;
    await api(`/noise-profiles/${id}`, 'DELETE');
    await loadNoiseProfiles();
}

async function loadNoisePresets() {
    noisePresets = await api('/noise-presets');
}

// ============== Output Channels ==============

async function loadOutputChannels(forceRender = true) {
    const newChannels = await api('/output-channels');
    const newJson = JSON.stringify(newChannels);
    
    // Check if any dropdown is currently focused or being interacted with
    const anySelectFocused = document.querySelector('select:focus');
    const shouldSkipRender = anySelectFocused || dropdownInteractionActive;
    
    if (forceRender || (newJson !== lastChannelsJson && !shouldSkipRender)) {
        // Preserve selected values for all dropdowns before re-rendering
        const selectedValues = {};
        document.querySelectorAll('.stream-select, .noise-select').forEach(select => {
            if (select.id && select.value) {
                selectedValues[select.id] = select.value;
            }
        });
        
        outputChannels = newChannels;
        lastChannelsJson = newJson;
        renderMainChannelGrid();
        
        // Restore selected values after rendering
        setTimeout(() => {
            Object.entries(selectedValues).forEach(([id, value]) => {
                const select = document.getElementById(id);
                if (select && Array.from(select.options).some(opt => opt.value === value)) {
                    select.value = value;
                }
            });
        }, 0);
        
        renderOutputChannelsList();
        updateGlobalPlayPauseButton();
    } else if (newJson !== lastChannelsJson) {
        // Data changed but dropdown is open - just update the data, don't re-render
        outputChannels = newChannels;
        lastChannelsJson = newJson;
        updateGlobalPlayPauseButton();
    }
}

function renderMainChannelGrid() {
    const container = document.getElementById('mainChannelGrid');
    
    if (outputChannels.length === 0) {
        container.innerHTML = `
            <div class="col-12 text-center text-muted py-5">
                <i class="bi bi-speaker display-1 mb-3 d-block opacity-50"></i>
                <p>No output channels configured yet.</p>
                <button class="btn btn-info" data-bs-toggle="modal" data-bs-target="#channelsConfigModal">
                    <i class="bi bi-plus-lg me-1"></i>Create Output Channel
                </button>
            </div>
        `;
        return;
    }
    
    container.innerHTML = outputChannels.map(ch => {
        const isPlaying = ch.is_playing && !ch.is_paused;
        const isPaused = ch.is_playing && ch.is_paused;
        const hasStream = ch.stream_id !== null;
        
        let statusClass = 'channel-idle';
        if (isPlaying) statusClass = 'channel-playing';
        else if (isPaused) statusClass = 'channel-paused';
        
        const trackInfo = ch.current_file ? `${ch.file_index + 1}/${ch.total_files}` : '';
        const volume = ch.volume !== undefined ? ch.volume : 1.0;
        const noiseEnabled = ch.noise_enabled || false;
        const noiseVolume = ch.noise_volume !== undefined ? ch.noise_volume : 0.3;
        
        return `
            <div class="col-12 col-md-6">
                <div class="channel-card ${statusClass}">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <div class="channel-name" title="${escapeHtml(ch.name)}">${escapeHtml(ch.name)}</div>
                        <select class="form-select form-select-sm stream-select" 
                                onchange="assignStreamToChannel(${ch.id}, this.value)"
                                id="channel-stream-${ch.id}">
                            <option value="">-- No Stream --</option>
                            ${streams.map(s => `<option value="${s.id}" ${ch.stream_id === s.id ? 'selected' : ''}>${escapeHtml(s.name)}</option>`).join('')}
                        </select>
                    </div>
                    
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <div class="d-flex gap-1 align-items-center">
                            <button class="btn btn-control-sm btn-test" onclick="testOutputChannel(${ch.id})" title="Test">
                                <i class="bi bi-volume-up"></i>
                            </button>
                            ${isPlaying ? `
                                <button class="btn btn-control-sm btn-pause" onclick="pauseChannel(${ch.id})" title="Pause">
                                    <i class="bi bi-pause-fill"></i>
                                </button>
                            ` : isPaused ? `
                                <button class="btn btn-control-sm btn-play" onclick="resumeChannel(${ch.id})" title="Resume">
                                    <i class="bi bi-play-fill"></i>
                                </button>
                            ` : `
                                <button class="btn btn-control-sm btn-play" onclick="playChannel(${ch.id})" title="Play" ${!hasStream || ch.total_files === 0 ? 'disabled' : ''}>
                                    <i class="bi bi-play-fill"></i>
                                </button>
                            `}
                            <button class="btn btn-control-sm btn-stop" onclick="stopChannel(${ch.id})" title="Stop" ${!hasStream ? 'disabled' : ''}>
                                <i class="bi bi-stop-fill"></i>
                            </button>
                            ${isPlaying ? `<span class="play-timer"><i class="bi bi-clock me-1"></i>${formatDuration(ch.play_duration || 0)}</span>` : ''}
                        </div>
                        ${trackInfo ? `<span class="track-info">${trackInfo}</span>` : ''}
                    </div>
                    
                    ${ch.current_file ? `
                    <div class="current-file-info mb-2">
                        <i class="bi bi-file-music me-1"></i>
                        <span title="${escapeHtml(ch.current_file)}">${escapeHtml(truncateFilename(ch.current_file, 30))}</span>
                        ${ch.in_delay ? '<span class="delay-badge ms-2">DELAY</span>' : ''}
                    </div>
                    ` : ''}
                    
                    <div class="volume-row mb-2">
                        <label class="small text-muted"><i class="bi bi-volume-up-fill me-1"></i>Vol</label>
                        <input type="range" class="form-range flex-grow-1" min="0" max="1" step="0.05" value="${volume}" 
                               onchange="setChannelVolume(${ch.id}, this.value)">
                        <span class="volume-value">${Math.round(volume * 100)}%</span>
                    </div>
                    
                    <div class="noise-row">
                        <div class="form-check form-check-inline">
                            <input class="form-check-input" type="checkbox" id="noise-${ch.id}" ${noiseEnabled ? 'checked' : ''}
                                   onchange="toggleNoise(${ch.id}, this.checked)">
                            <label class="form-check-label small text-muted" for="noise-${ch.id}">Noise</label>
                        </div>
                        <select class="form-select form-select-sm noise-select" id="noise-source-${ch.id}"
                                onchange="setNoiseSource(${ch.id}, this.value)" ${!noiseEnabled ? 'disabled' : ''}>
                            <option value="">-- Select --</option>
                            <optgroup label="Presets">
                                ${noisePresets.map(p => `<option value="preset:${p.id}" ${ch.noise_preset === p.id ? 'selected' : ''}>${escapeHtml(p.name)}</option>`).join('')}
                            </optgroup>
                            ${noiseProfiles.length > 0 ? `
                            <optgroup label="Custom">
                                ${noiseProfiles.map(p => `<option value="custom:${p.id}" ${!ch.noise_preset && ch.noise_profile_id === p.id ? 'selected' : ''}>${escapeHtml(p.name)}</option>`).join('')}
                            </optgroup>
                            ` : ''}
                        </select>
                        <input type="range" class="form-range noise-vol" min="0" max="1" step="0.05" value="${noiseVolume}"
                               onchange="setNoiseVolume(${ch.id}, this.value)" ${!noiseEnabled ? 'disabled' : ''} id="noise-vol-${ch.id}">
                        <span class="volume-value">${Math.round(noiseVolume * 100)}%</span>
                    </div>
                    
                    <div class="delay-row">
                        <label class="small text-muted"><i class="bi bi-clock me-1"></i>Delay</label>
                        <input type="range" class="form-range flex-grow-1" min="0" max="60" step="5" value="${ch.file_delay || 0}"
                               onchange="setChannelDelay(${ch.id}, this.value)" id="delay-${ch.id}">
                        <span class="delay-value">${ch.file_delay || 0}s</span>
                        <div class="form-check form-check-inline ms-2">
                            <input class="form-check-input" type="checkbox" id="noise-delay-${ch.id}" 
                                   ${ch.noise_during_delay ? 'checked' : ''}
                                   onchange="setNoiseDuringDelay(${ch.id}, this.checked)">
                            <label class="form-check-label small text-muted" for="noise-delay-${ch.id}" title="Play noise during delay">🔊</label>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

async function setChannelVolume(channelId, volume) {
    await api(`/output-channels/${channelId}/volume`, 'POST', { volume: parseFloat(volume) });
}

async function toggleNoise(channelId, enabled) {
    const sourceSelect = document.getElementById(`noise-source-${channelId}`);
    const volSlider = document.getElementById(`noise-vol-${channelId}`);
    sourceSelect.disabled = !enabled;
    volSlider.disabled = !enabled;
    
    const sourceValue = sourceSelect.value;
    let preset = null;
    let profileId = null;
    
    if (sourceValue.startsWith('preset:')) {
        preset = sourceValue.replace('preset:', '');
    } else if (sourceValue.startsWith('custom:')) {
        profileId = parseInt(sourceValue.replace('custom:', ''));
    }
    
    await api(`/output-channels/${channelId}/noise`, 'POST', { 
        enabled, 
        profile_id: profileId,
        preset: preset
    });
}

async function setNoiseSource(channelId, sourceValue) {
    let preset = null;
    let profileId = null;
    
    if (sourceValue.startsWith('preset:')) {
        preset = sourceValue.replace('preset:', '');
    } else if (sourceValue.startsWith('custom:')) {
        profileId = parseInt(sourceValue.replace('custom:', ''));
    }
    
    await api(`/output-channels/${channelId}/noise`, 'POST', { 
        enabled: true, 
        profile_id: profileId,
        preset: preset
    });
}

async function setNoiseVolume(channelId, volume) {
    await api(`/output-channels/${channelId}/noise`, 'POST', { 
        enabled: true, 
        noise_volume: parseFloat(volume) 
    });
}

async function setChannelDelay(channelId, delay) {
    const noiseDuringDelay = document.getElementById(`noise-delay-${channelId}`)?.checked || false;
    await api(`/output-channels/${channelId}/delay`, 'POST', { 
        delay: parseInt(delay),
        noise_during_delay: noiseDuringDelay
    });
}

async function setNoiseDuringDelay(channelId, enabled) {
    const delay = parseInt(document.getElementById(`delay-${channelId}`)?.value || 0);
    await api(`/output-channels/${channelId}/delay`, 'POST', { 
        delay: delay,
        noise_during_delay: enabled
    });
}

// Global controls
function getGlobalPlaybackState() {
    const playableChannels = outputChannels.filter(ch => ch.stream_id && ch.total_files > 0);
    const anyPlaying = playableChannels.some(ch => ch.is_playing && !ch.is_paused);
    const anyPaused = playableChannels.some(ch => ch.is_playing && ch.is_paused);
    return {
        playableChannels,
        anyPlaying,
        anyPaused
    };
}

function updateGlobalPlayPauseButton() {
    const btn = document.getElementById('playPauseAllBtn');
    const icon = document.getElementById('playPauseAllIcon');
    const label = document.getElementById('playPauseAllLabel');
    if (!btn || !icon || !label) return;

    const { playableChannels, anyPlaying, anyPaused } = getGlobalPlaybackState();

    if (playableChannels.length === 0) {
        btn.disabled = true;
        btn.classList.remove('btn-warning');
        btn.classList.add('btn-success');
        icon.className = 'bi bi-play-fill me-1';
        label.textContent = 'Play All';
        return;
    }

    btn.disabled = false;

    if (anyPlaying) {
        btn.classList.remove('btn-success');
        btn.classList.add('btn-warning');
        icon.className = 'bi bi-pause-fill me-1';
        label.textContent = 'Pause All';
    } else {
        btn.classList.remove('btn-warning');
        btn.classList.add('btn-success');
        icon.className = 'bi bi-play-fill me-1';
        label.textContent = anyPaused ? 'Resume All' : 'Play All';
    }
}

async function togglePlayPauseAll() {
    const { playableChannels, anyPlaying, anyPaused } = getGlobalPlaybackState();
    if (playableChannels.length === 0) {
        return;
    }

    if (anyPlaying) {
        await pauseAll();
    } else if (anyPaused) {
        await resumeAll();
    } else {
        await playAll();
    }
}

async function playAll() {
    for (const ch of outputChannels) {
        if (ch.stream_id && ch.total_files > 0) {
            await api(`/output-channels/${ch.id}/play`, 'POST');
        }
    }
    await loadOutputChannels(true);
}

async function pauseAll() {
    for (const ch of outputChannels) {
        if (ch.is_playing) {
            await api(`/output-channels/${ch.id}/pause`, 'POST');
        }
    }
    await loadOutputChannels(true);
}

async function resumeAll() {
    for (const ch of outputChannels) {
        if (ch.is_playing && ch.is_paused) {
            await api(`/output-channels/${ch.id}/resume`, 'POST');
        }
    }
    await loadOutputChannels(true);
}

async function stopAll() {
    for (const ch of outputChannels) {
        await api(`/output-channels/${ch.id}/stop`, 'POST');
    }
    await loadOutputChannels(true);
}

function renderOutputChannelsList() {
    const container = document.getElementById('outputChannelsList');
    if (!container) return;
    
    if (outputChannels.length === 0) {
        container.innerHTML = '<p class="text-muted text-center">No output channels created yet.</p>';
        return;
    }
    
    container.innerHTML = outputChannels.map(ch => {
        const deviceName = getDeviceName(ch.device_id);
        return `
            <div class="config-item d-flex justify-content-between align-items-center">
                <div>
                    <strong>${escapeHtml(ch.name)}</strong>
                    <div class="small text-muted">${escapeHtml(deviceName)}</div>
                </div>
                <div class="btn-group btn-group-sm">
                    <button class="btn btn-outline-info" onclick="testOutputChannel(${ch.id})" title="Test"><i class="bi bi-volume-up"></i></button>
                    <button class="btn btn-outline-secondary" onclick="editOutputChannel(${ch.id})"><i class="bi bi-pencil"></i></button>
                    <button class="btn btn-outline-danger" onclick="deleteOutputChannel(${ch.id})"><i class="bi bi-trash"></i></button>
                </div>
            </div>
        `;
    }).join('');
}

function getDeviceName(deviceId) {
    const device = devices.find(d => d.id === deviceId);
    return device ? device.name : `Device ${deviceId}`;
}

function showNewOutputChannelForm() {
    document.getElementById('outputChannelModalTitle').textContent = 'Create Output Channel';
    document.getElementById('outputChannelId').value = '';
    document.getElementById('outputChannelName').value = '';
    document.getElementById('outputChannelDevice').value = '';
    populateDeviceSelects();
    
    bootstrap.Modal.getInstance(document.getElementById('channelsConfigModal'))?.hide();
    new bootstrap.Modal(document.getElementById('outputChannelModal')).show();
}

function editOutputChannel(id) {
    const ch = outputChannels.find(c => c.id === id);
    if (!ch) return;
    
    document.getElementById('outputChannelModalTitle').textContent = 'Edit Output Channel';
    document.getElementById('outputChannelId').value = ch.id;
    document.getElementById('outputChannelName').value = ch.name;
    populateDeviceSelects();
    document.getElementById('outputChannelDevice').value = ch.device_id;
    
    bootstrap.Modal.getInstance(document.getElementById('channelsConfigModal'))?.hide();
    new bootstrap.Modal(document.getElementById('outputChannelModal')).show();
}

async function saveOutputChannel() {
    const id = document.getElementById('outputChannelId').value;
    const name = document.getElementById('outputChannelName').value.trim();
    const device_id = parseInt(document.getElementById('outputChannelDevice').value);
    
    if (!name || isNaN(device_id)) {
        alert('Please fill in all fields');
        return;
    }
    
    if (id) {
        await api(`/output-channels/${id}`, 'PUT', { name, device_id });
    } else {
        await api('/output-channels', 'POST', { name, device_id });
    }
    
    bootstrap.Modal.getInstance(document.getElementById('outputChannelModal')).hide();
    await loadOutputChannels(true);
}

async function deleteOutputChannel(id) {
    if (!confirm('Delete this output channel?')) return;
    
    try {
        await api(`/output-channels/${id}`, 'DELETE');
        await loadOutputChannels(true);
    } catch (e) {
        console.error('Delete error:', e);
        alert('Failed to delete channel');
    }
}

async function testOutputChannel(id) {
    await api(`/output-channels/${id}/test`, 'POST');
}

async function assignStreamToChannel(channelId, streamId) {
    const sid = streamId ? parseInt(streamId) : null;
    await api(`/output-channels/${channelId}/stream`, 'POST', { stream_id: sid });
    const ch = outputChannels.find(c => c.id === channelId);
    if (ch) {
        ch.stream_id = sid;
        lastChannelsJson = JSON.stringify(outputChannels);
    }
}

async function playChannel(channelId) {
    await api(`/output-channels/${channelId}/play`, 'POST');
    await loadOutputChannels(true);
}

async function pauseChannel(channelId) {
    await api(`/output-channels/${channelId}/pause`, 'POST');
    await loadOutputChannels(true);
}

async function resumeChannel(channelId) {
    await api(`/output-channels/${channelId}/resume`, 'POST');
    await loadOutputChannels(true);
}

async function stopChannel(channelId) {
    await api(`/output-channels/${channelId}/stop`, 'POST');
    await loadOutputChannels(true);
}

// ============== Streams ==============

async function loadStreams() {
    streams = await api('/streams');
    renderStreamsList();
    renderMainChannelGrid();
}

function renderStreamsList() {
    const container = document.getElementById('streamsList');
    if (!container) return;
    
    if (streams.length === 0) {
        container.innerHTML = '<p class="text-muted text-center">No streams created yet.</p>';
        return;
    }
    
    container.innerHTML = streams.map(stream => {
        return `
            <div class="config-item">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <div>
                        <strong>${escapeHtml(stream.name)}</strong>
                        ${stream.description ? `<div class="small text-muted">${escapeHtml(stream.description)}</div>` : ''}
                    </div>
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-outline-primary" onclick="showUploadModal(${stream.id})" title="Upload"><i class="bi bi-upload"></i></button>
                        <button class="btn btn-outline-secondary" onclick="showFilesModal(${stream.id})" title="Files"><i class="bi bi-files"></i></button>
                        <button class="btn btn-outline-secondary" onclick="editStream(${stream.id})"><i class="bi bi-pencil"></i></button>
                        <button class="btn btn-outline-danger" onclick="deleteStream(${stream.id})"><i class="bi bi-trash"></i></button>
                    </div>
                </div>
                <div class="small text-muted">
                    <i class="bi bi-file-music me-1"></i>${stream.files?.length || 0} files
                </div>
            </div>
        `;
    }).join('');
}

function showNewStreamForm() {
    document.getElementById('streamModalTitle').textContent = 'Create New Stream';
    document.getElementById('streamId').value = '';
    document.getElementById('streamName').value = '';
    document.getElementById('streamDescription').value = '';
    
    bootstrap.Modal.getInstance(document.getElementById('streamsConfigModal'))?.hide();
    new bootstrap.Modal(document.getElementById('streamModal')).show();
}

function editStream(id) {
    const stream = streams.find(s => s.id === id);
    if (!stream) return;
    
    document.getElementById('streamModalTitle').textContent = 'Edit Stream';
    document.getElementById('streamId').value = stream.id;
    document.getElementById('streamName').value = stream.name;
    document.getElementById('streamDescription').value = stream.description || '';
    
    bootstrap.Modal.getInstance(document.getElementById('streamsConfigModal'))?.hide();
    new bootstrap.Modal(document.getElementById('streamModal')).show();
}

async function saveStream() {
    const id = document.getElementById('streamId').value;
    const name = document.getElementById('streamName').value.trim();
    const description = document.getElementById('streamDescription').value.trim();
    
    if (!name) {
        alert('Please enter a stream name');
        return;
    }
    
    if (id) {
        await api(`/streams/${id}`, 'PUT', { name, description });
    } else {
        await api('/streams', 'POST', { name, description });
    }
    
    bootstrap.Modal.getInstance(document.getElementById('streamModal')).hide();
    await loadStreams();
}

async function deleteStream(id) {
    if (!confirm('Delete this stream and all its files?')) return;
    await api(`/streams/${id}`, 'DELETE');
    await loadStreams();
    await loadOutputChannels(true);
}

// ============== File Upload ==============

function showUploadModal(streamId) {
    document.getElementById('uploadStreamId').value = streamId;
    document.getElementById('audioFiles').value = '';
    document.getElementById('uploadProgress').classList.add('d-none');
    new bootstrap.Modal(document.getElementById('uploadModal')).show();
}

async function uploadFiles() {
    const streamId = document.getElementById('uploadStreamId').value;
    const files = document.getElementById('audioFiles').files;
    
    if (files.length === 0) {
        alert('Please select files to upload');
        return;
    }
    
    const progressDiv = document.getElementById('uploadProgress');
    const progressBar = document.getElementById('uploadProgressBar');
    const statusText = document.getElementById('uploadStatus');
    const uploadBtn = document.getElementById('uploadBtn');
    
    progressDiv.classList.remove('d-none');
    uploadBtn.disabled = true;
    
    let uploaded = 0;
    for (const file of files) {
        statusText.textContent = `Uploading ${file.name}...`;
        
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            await fetch(`/api/streams/${streamId}/upload`, {
                method: 'POST',
                body: formData
            });
            uploaded++;
            progressBar.style.width = `${(uploaded / files.length) * 100}%`;
        } catch (e) {
            console.error('Upload error:', e);
        }
    }
    
    statusText.textContent = `Uploaded ${uploaded} of ${files.length} files`;
    uploadBtn.disabled = false;
    
    setTimeout(async () => {
        bootstrap.Modal.getInstance(document.getElementById('uploadModal')).hide();
        await loadStreams();
    }, 1000);
}

// ============== Files Modal ==============

async function showFilesModal(streamId) {
    const stream = streams.find(s => s.id === streamId);
    if (!stream) return;
    
    document.getElementById('filesModalTitle').textContent = `Files: ${stream.name}`;
    document.getElementById('filesStreamId').value = streamId;
    
    const container = document.getElementById('filesContainer');
    
    if (!stream.files || stream.files.length === 0) {
        container.innerHTML = '<p class="text-muted text-center">No files in this stream</p>';
    } else {
        container.innerHTML = stream.files.map((file, index) => `
            <div class="file-item">
                <div>
                    <span class="text-muted me-2">${index + 1}.</span>
                    <span class="file-name-display">${escapeHtml(file.original_filename)}</span>
                </div>
                <button class="btn btn-sm btn-outline-danger" onclick="deleteFile(${file.id}, ${streamId})">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        `).join('');
    }
    
    new bootstrap.Modal(document.getElementById('filesModal')).show();
}

async function deleteFile(fileId, streamId) {
    if (!confirm('Delete this file?')) return;
    
    await api(`/files/${fileId}`, 'DELETE');
    await loadStreams();
    showFilesModal(streamId);
}

// ============== Utilities ==============

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDuration(seconds) {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    if (hrs > 0) {
        return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function truncateFilename(filename, maxLen) {
    if (!filename || filename.length <= maxLen) return filename;
    const ext = filename.lastIndexOf('.');
    if (ext > 0 && filename.length - ext <= 5) {
        const extPart = filename.substring(ext);
        const namePart = filename.substring(0, ext);
        const truncLen = maxLen - extPart.length - 3;
        return namePart.substring(0, truncLen) + '...' + extPart;
    }
    return filename.substring(0, maxLen - 3) + '...';
}
