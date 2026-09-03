const API = 'https://dhwani-api.onrender.com';
let wavesurfer = null;
let currentFileId = null;
let isPlaying = false;

// Elements
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const uploadScreen = document.getElementById('upload-screen');
const editorScreen = document.getElementById('editor-screen');
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const toast = document.getElementById('toast');

// Upload handling
dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('drag-over');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    if (e.dataTransfer.files.length) {
        uploadFile(e.dataTransfer.files[0]);
    }
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length) {
        uploadFile(e.target.files[0]);
    }
});

async function uploadFile(file) {
    showToast('Uploading...', 'success');
    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch(`${API}/upload`, { method: 'POST', body: formData });
        if (!res.ok) throw new Error('Upload failed');

        const data = await res.json();
        currentFileId = data.file_id;

        document.getElementById('file-name').textContent = data.filename;
        document.getElementById('file-meta').textContent =
            `${formatTime(data.duration)} | ${data.sample_rate}Hz | ${data.channels}ch${data.bpm ? ' | ' + Math.round(data.bpm) + ' BPM' : ''}`;

        uploadScreen.classList.remove('active');
        editorScreen.classList.add('active');

        initWaveform();
        loadVersions();
        showToast('File loaded successfully', 'success');
    } catch (err) {
        console.error('Upload error:', err);
        showToast('Failed to upload file', 'error');
    }
}

async function initWaveform() {
    const loading = document.getElementById('waveform-loading');

    if (wavesurfer) {
        wavesurfer.destroy();
    }

    wavesurfer = WaveSurfer.create({
        container: '#waveform',
        waveColor: '#555568',
        progressColor: '#7c5cff',
        cursorColor: '#a78bfa',
        barWidth: 2,
        barGap: 1,
        barRadius: 2,
        height: 100,
        dragToSeek: true,
        normalize: true,
    });

    wavesurfer.on('ready', (duration) => {
        loading.classList.add('hidden');
        document.getElementById('total-time').textContent = formatTime(duration);
    });

    wavesurfer.on('timeupdate', (currentTime) => {
        document.getElementById('current-time').textContent = formatTime(currentTime);
    });

    wavesurfer.on('play', () => {
        isPlaying = true;
        document.getElementById('btn-play').innerHTML = '&#9646;&#9646;';
        document.getElementById('btn-play').classList.add('playing');
    });

    wavesurfer.on('pause', () => {
        isPlaying = false;
        document.getElementById('btn-play').innerHTML = '&#9654;';
        document.getElementById('btn-play').classList.remove('playing');
    });

    wavesurfer.setVolume(0.8);
    wavesurfer.load(`${API}/audio/${currentFileId}`);
}

function togglePlay() {
    if (wavesurfer) {
        wavesurfer.playPause();
    }
}

function seekForward() {
    if (wavesurfer) {
        wavesurfer.setTime(wavesurfer.getCurrentTime() + 5);
    }
}

function seekBackward() {
    if (wavesurfer) {
        wavesurfer.setTime(wavesurfer.getCurrentTime() - 5);
    }
}

function setVolume(value) {
    if (wavesurfer) {
        wavesurfer.setVolume(value / 100);
    }
}

// Chat
async function sendMessage(e) {
    if (e) e.preventDefault();
    const msg = chatInput.value.trim();
    if (!msg || !currentFileId) return;

    chatInput.value = '';
    addMessage(msg, 'user');

    const typing = addTypingIndicator();

    try {
        const res = await fetch(`${API}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: currentFileId, message: msg }),
        });

        typing.remove();

        if (!res.ok) throw new Error('Chat failed');
        const data = await res.json();

        addMessage(data.reply, 'assistant', data.operation);
    } catch (err) {
        typing.remove();
        addMessage('Sorry, something went wrong.', 'assistant');
    }
}

function sendQuick(text) {
    chatInput.value = text;
    sendMessage();
}

function addMessage(text, role, operation = null) {
    const div = document.createElement('div');
    div.className = `message ${role}`;

    let html = `<div class="message-content">${escapeHtml(text)}</div>`;

    if (operation) {
        html += `
            <div class="message-operation">
                <pre>${JSON.stringify(operation, null, 2)}</pre>
            </div>
            <button class="apply-btn" onclick="applyOperation(this, ${escapeAttr(JSON.stringify(operation))})">
                Apply Changes
            </button>
        `;
    }

    div.innerHTML = html;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addTypingIndicator() {
    const div = document.createElement('div');
    div.className = 'message assistant';
    div.innerHTML = `
        <div class="message-content">
            <div class="typing-indicator">
                <span></span><span></span><span></span>
            </div>
        </div>
    `;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return div;
}

async function applyOperation(btn, operation) {
    btn.disabled = true;
    btn.textContent = 'Applying...';

    try {
        const res = await fetch(`${API}/apply`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: currentFileId, operation }),
        });

        if (!res.ok) throw new Error('Apply failed');
        const data = await res.json();

        btn.textContent = 'Applied!';
        btn.style.background = '#4ade80';

        wavesurfer.load(`${API}/audio/${currentFileId}`);
        await loadVersions();
        showToast(`Applied: Version ${data.version}`, 'success');
    } catch (err) {
        btn.textContent = 'Failed - Retry';
        btn.disabled = false;
        showToast('Failed to apply changes', 'error');
    }
}

async function loadVersions() {
    if (!currentFileId) return;

    try {
        const res = await fetch(`${API}/versions/${currentFileId}`);
        const data = await res.json();

        const list = document.getElementById('versions-list');
        list.innerHTML = '';

        const orig = document.createElement('div');
        orig.className = 'version-item active';
        orig.innerHTML = '<span class="version-dot"></span>Original';
        orig.onclick = () => loadVersion(null, orig);
        list.appendChild(orig);

        data.versions.forEach((v, i) => {
            const item = document.createElement('div');
            item.className = 'version-item';
            item.innerHTML = `<span class="version-dot"></span>v${v.version}: ${escapeHtml(v.operation)}`;
            item.onclick = () => loadVersion(v.version, item);
            list.appendChild(item);
        });
    } catch (err) {
        console.error('Failed to load versions');
    }
}

function loadVersion(version, element) {
    if (wavesurfer) {
        const suffix = version ? `?version=${version}` : '';
        wavesurfer.load(`${API}/audio/${currentFileId}${suffix}`);
    }

    document.querySelectorAll('.version-item').forEach(item => item.classList.remove('active'));
    if (element) element.classList.add('active');
}

// Utils
function formatTime(seconds) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function escapeAttr(str) {
    return str.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function showToast(msg, type = '') {
    toast.textContent = msg;
    toast.className = 'toast visible ' + type;
    setTimeout(() => {
        toast.classList.remove('visible');
    }, 3000);
}
