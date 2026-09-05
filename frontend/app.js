const API = location.hostname === 'localhost' || location.hostname === '127.0.0.1'
    ? `${location.protocol}//${location.hostname}:8000`
    : 'https://dhwani-bv20.onrender.com';

let wavesurfer = null;
let currentFileId = null;
let currentVersion = 0;
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
const chatToBottom = document.getElementById('chat-to-bottom');
const fabBadge = document.getElementById('fab-badge');

/* ── Upload: example cycler ── */
const EXAMPLES = [
    'Make it louder',
    'Add reverb at 0:30',
    'Trim the first 10 seconds',
    'Boost the bass',
    'Add compression',
    'Normalize the volume',
];
let exIdx = 0;
function cycleExamples() {
    const chip = document.getElementById('ex-chip');
    if (!chip) return;
    chip.classList.add('swap');
    setTimeout(() => {
        exIdx = (exIdx + 1) % EXAMPLES.length;
        chip.textContent = `\u201C${EXAMPLES[exIdx]}\u201D`;
        chip.classList.remove('swap');
    }, 260);
}
setInterval(cycleExamples, 2600);

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
    const dropZone = document.getElementById('drop-zone');
    const progressWrap = document.getElementById('upload-progress');
    const progressBar = document.getElementById('upload-progress-bar');
    const progressText = document.getElementById('upload-progress-text');
    const statusLabel = document.getElementById('upload-status-label');

    dropZone.classList.add('uploading');
    progressWrap.classList.remove('done', 'error');
    document.getElementById('upload-filename').textContent = file.name;
    progressBar.style.width = '0%';
    progressText.textContent = '0%';
    statusLabel.textContent = 'Uploading…';

    const formData = new FormData();
    formData.append('file', file);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API}/upload`);
    xhr.upload.onprogress = e => {
        if (!e.lengthComputable) return;
        const pct = Math.round((e.loaded / e.total) * 100);
        progressBar.style.width = pct + '%';
        progressText.textContent = pct + '%';
        if (pct >= 100) {
            progressBar.style.width = '100%';
            progressText.textContent = '100%';
            statusLabel.textContent = 'Processing…';
        }
    };
    xhr.onload = () => {
        if (xhr.status !== 200) {
            uploadFailed(progressWrap, progressBar, progressText, statusLabel);
            return;
        }
        const data = JSON.parse(xhr.responseText);
        currentFileId = data.file_id;
        currentVersion = 0;

        document.getElementById('file-name').textContent = data.filename;
        document.getElementById('file-meta').textContent =
            `${fmtTime(data.duration)} · ${data.sample_rate}Hz · ${data.channels}ch${data.bpm ? ' · ' + Math.round(data.bpm) + ' BPM' : ''}`;

        progressWrap.classList.add('done');
        statusLabel.textContent = 'Uploaded ✓';
        setTimeout(() => {
            dropZone.classList.remove('uploading');
            progressWrap.classList.remove('active', 'done');
            uploadScreen.classList.remove('active');
            editorScreen.classList.add('active');
            document.body.classList.add('app-editor');

            initWaveform();
            loadVersions();
            showToast('File loaded', 'success');
            if (window.innerWidth > 800) openChat();
        }, 900);
    };
    xhr.onerror = () => {
        uploadFailed(progressWrap, progressBar, progressText, statusLabel);
    };
    xhr.send(formData);
}

function uploadFailed(wrap, bar, text, label) {
    bar.style.width = '100%';
    text.textContent = 'Failed';
    label.textContent = 'Upload failed';
    wrap.classList.add('error');
    showToast('Upload failed', 'error');
}

/* ── Waveform ── */
function initWaveform() {
    const loading = document.getElementById('waveform-loading');
    if (wavesurfer) wavesurfer.destroy();

    initWaveformSparkles();

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
        const wrap = document.getElementById('waveform-wrap');
        if (wrap) wrap.classList.add('playing');
    });
    wavesurfer.on('pause', () => {
        isPlaying = false;
        const btn = document.getElementById('btn-play');
        btn.innerHTML = '&#9654;<span class="shortcut">Space</span>';
        btn.classList.remove('playing');
        const wrap = document.getElementById('waveform-wrap');
        if (wrap) wrap.classList.remove('playing');
    });

    wavesurfer.setVolume(0.8);
    wavesurfer.load(`${API}/audio/${currentFileId}`);
}

function initWaveformSparkles() {
    const wrap = document.getElementById('waveform-wrap');
    if (!wrap) return;
    let box = wrap.querySelector('.wf-sparkles');
    if (!box) {
        box = document.createElement('div');
        box.className = 'wf-sparkles';
        wrap.appendChild(box);
    }
    box.innerHTML = '';
    const glyphs = ['✦', '✧', '♪', '♫', '✺'];
    for (let i = 0; i < 14; i++) {
        const sp = document.createElement('span');
        sp.className = 'sp';
        sp.textContent = glyphs[Math.floor(Math.random() * glyphs.length)];
        sp.style.left = (4 + Math.random() * 92) + '%';
        sp.style.top = (8 + Math.random() * 70) + '%';
        sp.style.fontSize = (9 + Math.random() * 8) + 'px';
        sp.style.animationDelay = (Math.random() * 3) + 's';
        sp.style.animationDuration = (1.6 + Math.random() * 1.8) + 's';
        box.appendChild(sp);
    }
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
    if (!msg) return;
    if (!currentFileId) {
        showToast('Upload a file first', 'error');
        return;
    }
    chatInput.value = '';
    addMsg(msg, 'user');
    const typing = addTyping();
    setAvatarThinking(true);
    try {
        const res = await fetch(`${API}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: currentFileId, message: msg }),
        });
        typing.remove();
        setAvatarThinking(false);
        if (!res.ok) throw new Error('Chat failed');
        const data = await res.json();
        await addMsg(data.reply, 'assistant', data.operation);
        avatarPop();

        if (data.operation && window.innerWidth <= 800) {
            setTimeout(async () => {
                const ok = await applyOp(null, data.operation);
                if (ok) closeChat();
            }, 1000);
        }
    } catch {
        typing.remove();
        setAvatarThinking(false);
        addMsg('Something went wrong. Try again.', 'assistant');
    }
}

function sendQuick(t) { chatInput.value = t; sendMessage(); }

function setAvatarThinking(on) {
    const av = document.getElementById('ch-avatar');
    if (!av) return;
    av.classList.toggle('thinking', on);
}

function avatarPop() {
    const av = document.getElementById('ch-avatar');
    if (!av) return;
    av.classList.remove('pop');
    void av.offsetWidth;
    av.classList.add('pop');
}

function addMsg(text, role, operation = null) {
    const div = document.createElement('div');
    div.className = `msg ${role} msg-in`;
    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    div.appendChild(bubble);
    chatMessages.appendChild(div);
    scrollChatToBottom();

    if (role === 'assistant') {
        if (!chatPanel.classList.contains('open')) bumpUnread();
        return new Promise(resolve => {
            typeText(bubble, text, () => {
                if (operation && usableView(operation)) appendOperationCard(div, operation);
                resolve();
            });
        });
    }
    bubble.textContent = text;
    return Promise.resolve();
}

function usableView(op) {
    return op && typeof op === 'object' && typeof op.operation === 'string';
}

function typeText(el, text, done) {
    el.classList.add('typing-in');
    let i = 0;
    const STEP = 12;
    const speed = Math.max(5, Math.min(14, 4000 / Math.max(text.length, 1)));
    (function tick() {
        i += STEP;
        el.textContent = text.slice(0, i);
        scrollChatToBottom();
        if (i < text.length) {
            setTimeout(tick, speed);
        } else {
            el.classList.remove('typing-in');
            if (done) done();
        }
    })();
}

function appendOperationCard(div, operation) {
    const { icon, label, detail } = getOpLabel(operation);
    const card = document.createElement('div');
    card.className = 'op-card';
    card.innerHTML = `
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
        </button>`;
    div.appendChild(card);
    scrollChatToBottom();
}

function addTyping() {
    const div = document.createElement('div');
    div.className = 'msg assistant';
    div.innerHTML = `<div class="msg-bubble"><div class="typing"><span></span><span></span><span></span></div></div>`;
    chatMessages.appendChild(div);
    scrollChatToBottom();
    return div;
}

/* ── Apply ── */
async function applyOp(btn, op) {
    if (btn) {
        btn.disabled = true;
        btn.classList.add('loading');
    }
    try {
        const res = await fetch(`${API}/apply`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: currentFileId, operation: op }),
        });
        if (!res.ok) throw new Error('Apply failed');
        const data = await res.json();
        currentVersion = data.version;
        if (btn) {
            btn.classList.remove('loading');
            btn.querySelector('.btn-label').textContent = 'Applied ✓';
            btn.style.background = 'var(--success)';
            spawnBurst(btn);
        }
        showWaveformLoading();
        wavesurfer.load(`${API}/audio/${currentFileId}`);
        await loadVersions();
        showToast(`Version ${data.version} applied`, 'success');
        return true;
    } catch {
        if (btn) {
            btn.classList.remove('loading');
            btn.disabled = false;
            btn.querySelector('.btn-label').textContent = 'Retry';
        }
        showToast('Apply failed', 'error');
        return false;
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

        const orig = mkEl('div', 'v-item',
            '<span class="v-dot"></span><span class="v-label">Original</span><button class="v-dl" title="Download" onclick="event.stopPropagation(); downloadVer(0)">&#11015;</button>');
        orig.dataset.version = '0';
        orig.onclick = () => { loadVer(0, orig); };
        list.appendChild(orig);

        data.versions.forEach(v => {
            const item = mkEl('div', 'v-item',
                `<span class="v-dot"></span><span class="v-label">v${v.version}: ${esc(v.operation)}</span><button class="v-dl" title="Download" onclick="event.stopPropagation(); downloadVer(${v.version})">&#11015;</button>`);
            item.dataset.version = String(v.version);
            item.onclick = () => { loadVer(v.version, item); };
            list.appendChild(item);
        });

        document.querySelectorAll('.v-item').forEach(i =>
            i.classList.toggle('active', i.dataset.version === String(currentVersion)));
        setVersionsActive(currentVersion ? `v${currentVersion}` : 'v0');
    } catch (err) {
        console.error('Failed to load versions');
    }
}

function setVersionsActive(label) {
    const el = document.getElementById('fi-versions-label');
    if (el) el.textContent = label;
}

function toggleVersions() {
    document.getElementById('versions-dropdown').classList.toggle('open');
    document.getElementById('fi-versions').classList.toggle('open');
}

function closeVersions() {
    document.getElementById('versions-dropdown').classList.remove('open');
    document.getElementById('fi-versions').classList.remove('open');
}

function showWaveformLoading() {
    const loading = document.getElementById('waveform-loading');
    if (loading) loading.classList.remove('hidden');
}

function loadVer(version, el) {
    currentVersion = version || 0;
    showWaveformLoading();
    if (wavesurfer) {
        const q = version ? `?version=${version}` : '?version=0';
        wavesurfer.load(`${API}/audio/${currentFileId}${q}`);
    }
    document.querySelectorAll('.v-item').forEach(i => i.classList.remove('active'));
    if (el) el.classList.add('active');
    setVersionsActive(currentVersion ? `v${currentVersion}` : 'v0');
    closeVersions();
}

function downloadVer(version) {
    const q = version ? `?version=${version}` : '?version=0';
    const a = document.createElement('a');
    a.href = `${API}/download/${currentFileId}${q}`;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    a.remove();
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
    const info = map[op.operation] || { icon: '🔧', label: op.operation || 'Edit', detail: () => null };
    return { icon: info.icon, label: info.label, detail: info.detail() };
}

/* ── Chat Scroll-to-Bottom Badge ── */
function scrollChatToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
    chatToBottom.classList.remove('visible');
}

chatMessages.addEventListener('scroll', () => {
    const distFromBottom = chatMessages.scrollHeight - chatMessages.scrollTop - chatMessages.clientHeight;
    if (distFromBottom > 80) {
        chatToBottom.classList.add('visible');
    } else {
        chatToBottom.classList.remove('visible');
    }
}, { passive: true });

/* ── Chat Open / Close ── */
function openChat() {
    if (!chatPanel || !chatFab) return;
    chatPanel.classList.add('open');
    chatFab.classList.add('active');
    document.body.classList.add('chat-open');
    clearUnread();
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function closeChat() {
    if (!chatPanel || !chatFab) return;
    chatPanel.classList.remove('open');
    chatFab.classList.remove('active');
    document.body.classList.remove('chat-open');
}

function toggleChat() {
    if (!chatPanel || !chatFab) return;
    chatPanel.classList.contains('open') ? closeChat() : openChat();
}

function bumpUnread() {
    if (!fabBadge || !chatFab) return;
    const n = parseInt(fabBadge.dataset.count || '0', 10) + 1;
    fabBadge.dataset.count = n;
    fabBadge.textContent = n > 9 ? '9+' : n;
    chatFab.classList.add('has-unread');
}

function clearUnread() {
    if (!fabBadge || !chatFab) return;
    fabBadge.dataset.count = '0';
    fabBadge.textContent = '';
    chatFab.classList.remove('has-unread');
}

/* ── Chat Collapse ── */
function toggleChatPanel() {
    chatPanel.classList.toggle('collapsed');
    const chevron = document.getElementById('chat-chevron');
    const toggle = document.getElementById('chat-toggle');
    const collapsed = chatPanel.classList.contains('collapsed');
    chevron.innerHTML = collapsed ? '&#9652;' : '&#9662;';
    toggle.title = collapsed ? 'Expand' : 'Collapse';
    if (!collapsed) chatMessages.scrollTop = chatMessages.scrollHeight;
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

/* ── Magic: sparkle burst ── */
function spawnBurst(el) {
    const rect = el.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    for (let i = 0; i < 12; i++) {
        const s = document.createElement('span');
        s.className = 'sp-burst';
        const ang = (Math.PI * 2 * i) / 12 + Math.random() * 0.5;
        const dist = 40 + Math.random() * 40;
        s.style.left = x + 'px';
        s.style.top = y + 'px';
        s.style.setProperty('--bx', Math.cos(ang) * dist + 'px');
        s.style.setProperty('--by', Math.sin(ang) * dist + 'px');
        s.style.background = Math.random() > 0.5
            ? 'var(--accent-start)'
            : 'var(--accent-end)';
        document.body.appendChild(s);
        setTimeout(() => s.remove(), 750);
    }
}

/* ── Magic: cursor sparkle trail ── */
let lastTrail = 0;
document.addEventListener('mousemove', e => {
    const now = performance.now();
    if (now - lastTrail < 40) return;
    lastTrail = now;
    const s = document.createElement('span');
    s.className = 'sp-trail';
    s.style.left = (e.clientX + (Math.random() - 0.5) * 8) + 'px';
    s.style.top = (e.clientY + (Math.random() - 0.5) * 8) + 'px';
    document.body.appendChild(s);
    setTimeout(() => s.remove(), 650);
});
