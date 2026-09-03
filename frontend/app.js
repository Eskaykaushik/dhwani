const API = location.hostname === 'localhost' || location.hostname === '127.0.0.1'
    ? `${location.protocol}//${location.hostname}:8000`
    : 'https://dhwani-api.onrender.com';

let wavesurfer = null;
let currentFileId = null;
let isPlaying = false;
let isMuted = false;
let lastVolume = 80;

const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const uploadScreen = document.getElementById('upload-screen');
const editorScreen = document.getElementById('editor-screen');
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const toast = document.getElementById('toast');
const chatPanel = document.getElementById('chat-panel');
const chatFab = document.getElementById('chat-fab');

/* ── Upload ── */
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', e => { if (e.target.files.length) uploadFile(e.target.files[0]); });

function uploadFile(file) {
    const progressWrap = document.getElementById('upload-progress');
    const progressBar = document.getElementById('upload-progress-bar');
    const progressText = document.getElementById('upload-progress-text');
    progressWrap.classList.add('active');
    progressBar.style.width = '0%';
    progressText.textContent = '0%';

    const formData = new FormData();
    formData.append('file', file);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API}/upload`);
    xhr.upload.onprogress = e => {
        if (e.lengthComputable) {
            const pct = Math.round((e.loaded / e.total) * 100);
            progressBar.style.width = pct + '%';
            progressText.textContent = pct + '%';
        }
    };
    xhr.onload = () => {
        progressWrap.classList.remove('active');
        if (xhr.status !== 200) { showToast('Upload failed', 'error'); return; }
        const data = JSON.parse(xhr.responseText);
        currentFileId = data.file_id;

        document.getElementById('file-name').textContent = data.filename;
        document.getElementById('file-meta').textContent =
            `${fmtTime(data.duration)} · ${data.sample_rate}Hz · ${data.channels}ch${data.bpm ? ' · ' + Math.round(data.bpm) + ' BPM' : ''}`;

        uploadScreen.classList.remove('active');
        editorScreen.classList.add('active');

        initWaveform();
        loadVersions();
        showToast('File loaded', 'success');
    };
    xhr.onerror = () => { progressWrap.classList.remove('active'); showToast('Upload failed', 'error'); };
    xhr.send(formData);
}

/* ── Waveform ── */
function initWaveform() {
    const loading = document.getElementById('waveform-loading');
    if (wavesurfer) wavesurfer.destroy();

    wavesurfer = WaveSurfer.create({
        container: '#waveform',
        waveColor: 'rgba(99,102,241,0.35)',
        progressColor: 'rgba(20,184,166,0.8)',
        cursorColor: '#14b8a6',
        barWidth: 2, barGap: 1, barRadius: 2,
        height: 80, dragToSeek: true, normalize: true,
    });

    wavesurfer.on('ready', dur => {
        loading.classList.add('hidden');
        document.getElementById('total-time').textContent = fmtTime(dur);
    });
    wavesurfer.on('timeupdate', t => {
        document.getElementById('current-time').textContent = fmtTime(t);
    });
    wavesurfer.on('play', () => {
        isPlaying = true;
        const btn = document.getElementById('btn-play');
        btn.innerHTML = '&#9646;&#9646;<span class="shortcut">Space</span>';
        btn.classList.add('playing');
    });
    wavesurfer.on('pause', () => {
        isPlaying = false;
        const btn = document.getElementById('btn-play');
        btn.innerHTML = '&#9654;<span class="shortcut">Space</span>';
        btn.classList.remove('playing');
    });

    wavesurfer.setVolume(0.8);
    wavesurfer.load(`${API}/audio/${currentFileId}`);
}

/* ── Playback ── */
function togglePlay() { if (wavesurfer) wavesurfer.playPause(); }
function seekForward() { if (wavesurfer) wavesurfer.setTime(wavesurfer.getCurrentTime() + 5); }
function seekBackward() { if (wavesurfer) wavesurfer.setTime(Math.max(0, wavesurfer.getCurrentTime() - 5)); }
function setVolume(v) { if (wavesurfer) wavesurfer.setVolume(v / 100); }

function toggleMute() {
    if (!wavesurfer) return;
    isMuted = !isMuted;
    const icon = document.getElementById('vol-toggle');
    const slider = document.getElementById('volume-slider');
    if (isMuted) {
        lastVolume = parseInt(slider.value);
        wavesurfer.setVolume(0);
        slider.value = 0;
        icon.innerHTML = '&#128263;';
    } else {
        wavesurfer.setVolume(lastVolume / 100);
        slider.value = lastVolume;
        icon.innerHTML = '&#128266;';
    }
}

/* ── Keyboard Shortcuts ── */
document.addEventListener('keydown', e => {
    const inInput = document.activeElement === chatInput;
    if (inInput) return; // don't capture when typing

    if (e.code === 'Space') { e.preventDefault(); togglePlay(); }
    if (e.code === 'ArrowRight') { e.preventDefault(); e.shiftKey ? seekForwardN(10) : seekForward(); }
    if (e.code === 'ArrowLeft') { e.preventDefault(); e.shiftKey ? seekBackwardN(10) : seekBackward(); }
});

function seekForwardN(s) { if (wavesurfer) wavesurfer.setTime(wavesurfer.getCurrentTime() + s); }
function seekBackwardN(s) { if (wavesurfer) wavesurfer.setTime(Math.max(0, wavesurfer.getCurrentTime() - s)); }

/* ── Chat ── */
async function sendMessage(e) {
    if (e) e.preventDefault();
    const msg = chatInput.value.trim();
    if (!msg || !currentFileId) return;
    chatInput.value = '';
    addMsg(msg, 'user');
    const typing = addTyping();
    try {
        const res = await fetch(`${API}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: currentFileId, message: msg }),
        });
        typing.remove();
        if (!res.ok) throw new Error('Chat failed');
        const data = await res.json();
        addMsg(data.reply, 'assistant', data.operation);
    } catch {
        typing.remove();
        addMsg('Something went wrong. Try again.', 'assistant');
    }
}

function sendQuick(t) { chatInput.value = t; sendMessage(); }

function addMsg(text, role, operation = null) {
    const div = document.createElement('div');
    div.className = `msg ${role}`;
    let html = `<div class="msg-bubble">${esc(text)}</div>`;

    if (operation) {
        const { icon, label, detail } = getOpLabel(operation);
        html += `
            <div class="op-card">
                <div class="op-header">
                    <span class="op-icon">${icon}</span>
                    <span>${label}</span>
                </div>
                ${detail ? `<span class="op-detail">${detail}</span>` : ''}
                <span class="op-raw" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'">{ } raw</span>
                <pre style="display:none;font-size:10px;color:var(--text-muted);margin:0;white-space:pre-wrap;">${JSON.stringify(operation)}</pre>
                <button class="apply-btn" onclick="applyOp(this, ${escAttr(JSON.stringify(operation))})">
                    <span class="btn-label">Apply</span>
                    <span class="spinner"></span>
                </button>
            </div>`;
    }

    div.innerHTML = html;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addTyping() {
    const div = document.createElement('div');
    div.className = 'msg assistant';
    div.innerHTML = `<div class="msg-bubble"><div class="typing"><span></span><span></span><span></span></div></div>`;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return div;
}

/* ── Apply ── */
async function applyOp(btn, op) {
    btn.disabled = true;
    btn.classList.add('loading');
    try {
        const res = await fetch(`${API}/apply`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: currentFileId, operation: op }),
        });
        if (!res.ok) throw new Error('Apply failed');
        const data = await res.json();
        btn.classList.remove('loading');
        btn.querySelector('.btn-label').textContent = 'Applied ✓';
        btn.style.background = 'var(--success)';
        wavesurfer.load(`${API}/audio/${currentFileId}`);
        await loadVersions();
        showToast(`Version ${data.version} applied`, 'success');
    } catch {
        btn.classList.remove('loading');
        btn.disabled = false;
        btn.querySelector('.btn-label').textContent = 'Retry';
        showToast('Apply failed', 'error');
    }
}

/* ── Versions ── */
async function loadVersions() {
    if (!currentFileId) return;
    try {
        const res = await fetch(`${API}/versions/${currentFileId}`);
        const data = await res.json();
        const list = document.getElementById('versions-list');
        list.innerHTML = '';

        const orig = mkEl('div', 'v-item active', '<span class="v-dot"></span><span class="v-label">Original</span>');
        orig.onclick = () => { loadVer(null, orig); };
        list.appendChild(orig);

        data.versions.forEach(v => {
            const item = mkEl('div', 'v-item',
                `<span class="v-dot"></span><span class="v-label">v${v.version}: ${esc(v.operation)}</span>`);
            item.onclick = () => { loadVer(v.version, item); };
            list.appendChild(item);
        });
    } catch (err) {
        console.error('Failed to load versions');
    }
}

function loadVer(version, el) {
    if (wavesurfer) {
        const q = version ? `?version=${version}` : '';
        wavesurfer.load(`${API}/audio/${currentFileId}${q}`);
    }
    document.querySelectorAll('.v-item').forEach(i => i.classList.remove('active'));
    if (el) el.classList.add('active');
}

/* ── Operation Labels ── */
function getOpLabel(op) {
    const map = {
        trim:    { icon: '✂️', label: 'Trim', detail: () => `${fmtTime(op.start||0)} → ${fmtTime(op.end||0)}` },
        volume:  { icon: '🔊', label: 'Volume', detail: () => `${op.gain>0?'+':''}${op.gain} dB` },
        fade_in: { icon: '📈', label: 'Fade In', detail: () => `${op.duration||1}s` },
        fade_out:{ icon: '📉', label: 'Fade Out', detail: () => `${op.duration||1}s` },
        normalize:{ icon: '📊', label: 'Normalize', detail: () => null },
        eq:      { icon: '🎛️', label: 'EQ', detail: () => `${op.frequency||1000}Hz ${op.gain>0?'+':''}${op.gain||0}dB` },
        compress:{ icon: '📐', label: 'Compress', detail: () => `${op.threshold||-20}dB ratio ${op.ratio||4}:1` },
        reverb:  { icon: '🌊', label: 'Reverb', detail: () => `wet ${Math.round((op.wet||0.5)*100)}%` },
        delay:   { icon: '⏱️', label: 'Delay', detail: () => `${op.delay_time||0.5}s feedback ${Math.round((op.feedback||0.3)*100)}%` },
        pitch:   { icon: '🎵', label: 'Pitch', detail: () => `${op.semitones>0?'+':''}${op.semitones} semitones` },
        tempo:   { icon: '⚡', label: 'Tempo', detail: () => `${op.factor||1}x` },
        layer:   { icon: '🎚️', label: 'Layer', detail: () => op.file_id || '' },
    };
    const info = map[op.operation] || { icon: '🔧', label: op.operation, detail: () => null };
    return { icon: info.icon, label: info.label, detail: info.detail() };
}

/* ── Mobile Chat Toggle ── */
function toggleChat() {
    chatPanel.classList.toggle('open');
    chatFab.classList.toggle('active');
    chatFab.innerHTML = chatPanel.classList.contains('open')
        ? '&#10005;'
        : '&#128172;<span class="fab-badge" id="fab-badge"></span>';
}

/* ── Utils ── */
function fmtTime(s) {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, '0')}`;
}
function esc(t) { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; }
function escAttr(s) { return s.replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
function mkEl(tag, cls, html) {
    const el = document.createElement(tag);
    el.className = cls;
    el.innerHTML = html;
    return el;
}
function showToast(msg, type = '') {
    toast.textContent = msg;
    toast.className = 'toast visible ' + type;
    setTimeout(() => toast.classList.remove('visible'), 3000);
}
