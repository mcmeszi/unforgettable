const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

let activeSessionId = $('.recorder')?.dataset.sessionId || '';
let recording = false;
let startedAt = null;
let timerHandle = null;
let recognition = null;
let lastOutput = null;
let mediaRecorder = null;
let mediaStream = null;
let audioChunks = [];
let busy = false;

async function api(url, payload = null) {
    const options = payload
        ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }
        : {};
    const response = await fetch(url, options);
    const text = await response.text();
    let data = {};
    try {
        data = text ? JSON.parse(text) : {};
    } catch (_) {
        data = { error: text || 'Érvénytelen API válasz' };
    }
    if (!response.ok || data.ok === false) {
        throw new Error(data.error || 'API hiba');
    }
    return data;
}

function escapeHtml(value) {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

function updateTimer() {
    if (!startedAt) return;
    const seconds = Math.floor((Date.now() - startedAt) / 1000);
    const h = String(Math.floor(seconds / 3600)).padStart(2, '0');
    const m = String(Math.floor((seconds % 3600) / 60)).padStart(2, '0');
    const s = String(seconds % 60).padStart(2, '0');
    $('#timer').textContent = `${h}:${m}:${s}`;
}

function setPreview(text) {
    const preview = $('#outputPreview');
    if (preview) preview.textContent = text;
}

function setProviderStatus(text) {
    const status = $('#providerStatus');
    if (status) status.textContent = text;
}

function setRecorderBusy(nextBusy) {
    busy = nextBusy;
    ['#recordButton', '#stopBtn', '#newSession', '#importantBtn', '#researchBtn'].forEach((selector) => {
        const el = $(selector);
        if (el) el.toggleAttribute('disabled', nextBusy);
    });
}

function draftKey(id = activeSessionId) {
    return id ? `unforgettable:draft:${id}` : 'unforgettable:draft:new';
}

function saveDraft() {
    const input = $('#transcriptInput');
    if (input) localStorage.setItem(draftKey(), input.value);
}

function clearDraft(id = activeSessionId) {
    localStorage.removeItem(draftKey(id));
}

function restoreDraft() {
    const input = $('#transcriptInput');
    if (!input) return;
    const draft = localStorage.getItem(draftKey());
    if (draft && input.value.trim() === '') {
        input.value = draft;
        setPreview('Visszatöltöttem a lokális draftot.');
    }
}

function setupSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return null;
    const rec = new SpeechRecognition();
    rec.lang = $('.recorder')?.dataset.speechLanguage || 'hu-HU';
    rec.continuous = true;
    rec.interimResults = true;
    rec.onresult = (event) => {
        let finalText = '';
        let interim = '';
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) finalText += transcript + ' ';
            else interim += transcript;
        }
        const input = $('#transcriptInput');
        if (finalText) input.value = `${input.value} ${finalText}`.trim();
        $('#outputPreview') && ($('#outputPreview').textContent = interim || input.value || 'Hallgatok.');
    };
    rec.onerror = () => {
        recording = false;
        $('#recordButton')?.classList.remove('recording');
    };
    return rec;
}

function audioProvider() {
    return $('.recorder')?.dataset.audioProvider || 'browser';
}

async function startMediaRecorder() {
    if (!navigator.mediaDevices || !window.MediaRecorder) {
        throw new Error('A böngésző nem támogatja a MediaRecordert.');
    }
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];
    const preferred = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : '';
    mediaRecorder = new MediaRecorder(mediaStream, preferred ? { mimeType: preferred } : undefined);
    mediaRecorder.addEventListener('dataavailable', (event) => {
        if (event.data.size > 0) audioChunks.push(event.data);
    });
    mediaRecorder.start();
}

async function stopMediaRecorder() {
    if (!mediaRecorder || mediaRecorder.state === 'inactive') return null;
    const stopped = new Promise((resolve) => mediaRecorder.addEventListener('stop', resolve, { once: true }));
    mediaRecorder.stop();
    await stopped;
    mediaStream?.getTracks().forEach((track) => track.stop());
    mediaStream = null;
    const type = audioChunks[0]?.type || 'audio/webm';
    return new Blob(audioChunks, { type });
}

async function transcribeAudio(blob) {
    const form = new FormData();
    const extension = blob.type.includes('mp4') ? 'mp4' : 'webm';
    form.append('audio', blob, `unforgettable.${extension}`);
    const response = await fetch('/api/transcribe.php', { method: 'POST', body: form });
    const data = await response.json();
    if (!response.ok || data.ok === false) throw new Error(data.error || 'Transcribe hiba');
    return data.raw_transcript || '';
}

async function ensureSession() {
    if (activeSessionId) return activeSessionId;
    const data = await api('/api/session-create.php', {});
    activeSessionId = data.session.id;
    $('.recorder') && ($('.recorder').dataset.sessionId = activeSessionId);
    restoreDraft();
    return activeSessionId;
}

async function startRecording() {
    if (busy || recording) return;
    setRecorderBusy(true);
    try {
        await ensureSession();
        recording = true;
        startedAt = Date.now();
        timerHandle = setInterval(updateTimer, 1000);
        updateTimer();
        $('#recordButton')?.classList.add('recording');
        if (audioProvider() === 'elevenlabs') {
            try {
                await startMediaRecorder();
                setProviderStatus('ElevenLabs STT: audio rögzítés fut');
            } catch (error) {
                setProviderStatus('MediaRecorder nem elérhető, böngészős fallback');
                recognition = recognition || setupSpeechRecognition();
                try { recognition?.start(); } catch (_) {}
            }
        } else {
            recognition = recognition || setupSpeechRecognition();
            try { recognition?.start(); } catch (_) {}
        }
        setPreview('Rögzítés fut. A csend is maradhat csend.');
    } catch (error) {
        recording = false;
        clearInterval(timerHandle);
        $('#recordButton')?.classList.remove('recording');
        setProviderStatus(error.message);
        setPreview(`Nem sikerült elindítani: ${error.message}`);
    } finally {
        setRecorderBusy(false);
    }
}

async function stopRecording() {
    if (!activeSessionId || busy) return;
    setRecorderBusy(true);
    const wasRecording = recording;
    recording = false;
    clearInterval(timerHandle);
    $('#recordButton')?.classList.remove('recording');
    try { recognition?.stop(); } catch (_) {}
    let raw = ($('#transcriptInput')?.value || '').trim();
    if (audioProvider() === 'elevenlabs' && wasRecording) {
        try {
            const blob = await stopMediaRecorder();
            if (blob && blob.size > 0) {
                setProviderStatus('ElevenLabs STT feldolgozás...');
                const sttText = await transcribeAudio(blob);
                raw = [raw, sttText].filter(Boolean).join('\n\n');
                $('#transcriptInput') && ($('#transcriptInput').value = raw);
                saveDraft();
            }
        } catch (error) {
            setProviderStatus(error.message);
        }
    }
    try {
        if (raw === '') {
            throw new Error('Üres sessiont nem zárok le. Írj vagy rögzíts legalább egy mondatot.');
        }
        const data = await api('/api/session-close.php', { id: activeSessionId, raw_transcript: raw });
        lastOutput = data.output;
        clearDraft(activeSessionId);
        setPreview(data.output.markdown);
        window.setTimeout(() => window.location.href = `/app/session.php?id=${encodeURIComponent(activeSessionId)}`, 700);
    } catch (error) {
        saveDraft();
        setProviderStatus('Lezárás megállt, draft megőrizve.');
        setPreview(error.message);
    } finally {
        setRecorderBusy(false);
    }
}

$('#newSession')?.addEventListener('click', async () => {
    if (busy) return;
    setRecorderBusy(true);
    try {
        const data = await api('/api/session-create.php', {});
        activeSessionId = data.session.id;
        $('.recorder').dataset.sessionId = activeSessionId;
        $('#transcriptInput').value = '';
        clearDraft(activeSessionId);
        setPreview('Új session készen áll.');
    } catch (error) {
        setPreview(error.message);
    } finally {
        setRecorderBusy(false);
    }
});

$('#recordButton')?.addEventListener('click', () => {
    (recording ? stopRecording() : startRecording()).catch((error) => setPreview(error.message));
});
$('#stopBtn')?.addEventListener('click', stopRecording);

$('#importantBtn')?.addEventListener('click', async () => {
    try {
        await ensureSession();
        await api('/api/session-update.php', { id: activeSessionId, important: true });
        setPreview('Fontos sessionként mentve. Nem kommentálom, csak őrzöm.');
    } catch (error) {
        setPreview(error.message);
    }
});

$('#readBackBtn')?.addEventListener('click', () => {
    const text = ($('#transcriptInput')?.value || '').trim();
    const excerpt = text.split(/\s+/).slice(-45).join(' ');
    setPreview(excerpt || 'Nincs még visszaolvasható rész.');
});

$('#researchBtn')?.addEventListener('click', async () => {
    try {
        await ensureSession();
        const query = prompt('Mit nézzek utána?');
        if (!query) return;
        const data = await api('/api/research.php', { id: activeSessionId, query });
        setPreview(data.research.results.map((r, i) => `${i + 1}. ${r.title}\n${r.summary}`).join('\n\n'));
    } catch (error) {
        setPreview(error.message);
    }
});

$('#copyChatGPT')?.addEventListener('click', async () => {
    if (!lastOutput?.chatgpt_prompt) return;
    await navigator.clipboard.writeText(lastOutput.chatgpt_prompt);
    setPreview('ChatGPT folytató prompt másolva.');
});

$('#continueSession')?.addEventListener('click', () => {
    const id = $('.session-detail')?.dataset.sessionId;
    window.location.href = `/app/index.php?continue=${encodeURIComponent(id || '')}`;
});

$('#saveEdited')?.addEventListener('click', async () => {
    const id = $('.session-detail')?.dataset.sessionId;
    await api('/api/session-update.php', { id, user_edited_output: $('#editedOutput')?.value || '' });
    alert('Szerkesztett output külön rétegként mentve.');
});

$('#generateDigest')?.addEventListener('click', async () => {
    const data = await api('/api/digest-generate.php', {});
    alert(`Digest elkészült: ${data.date}`);
});

$('#generateOutput')?.addEventListener('click', async () => {
    const id = $('.session-detail')?.dataset.sessionId;
    const data = await api('/api/generate-output.php', { id });
    $('#editedOutput').value = data.output.markdown;
    $('#sessionPrompt').textContent = data.output.chatgpt_prompt;
    alert(`Új output készült: v${data.output.version}`);
});

$('#sendNotes')?.addEventListener('click', async () => {
    const id = $('.session-detail')?.dataset.sessionId;
    const data = await api('/api/notes-export.php', { id });
    await navigator.clipboard.writeText(data.content || '');
    alert('Notes tartalom előkészítve és vágólapra másolva.');
});

$('#sendDrive')?.addEventListener('click', async () => {
    const id = $('.session-detail')?.dataset.sessionId;
    const data = await api('/api/drive-upload.php', { id });
    alert(`Drive export státusz: ${data.drive.status}`);
});

async function dispatchAction(action, extra = {}) {
    const id = $('.session-detail')?.dataset.sessionId;
    const status = $('#actionStatus');
    status && (status.textContent = 'Akció fut...');
    try {
        const data = await api('/api/action-dispatch.php', { id, action, ...extra });
        status && (status.textContent = JSON.stringify(data.result, null, 2));
        return data.result;
    } catch (error) {
        status && (status.textContent = error.message);
        throw error;
    }
}

$('#sendEmail')?.addEventListener('click', async () => {
    const to = prompt('Melyik email címre küldjem? Üresen hagyva az alapértelmezett címzettet használom.', '');
    if (to === null) return;
    await dispatchAction('email', { to });
});

$('#createGoogleDoc')?.addEventListener('click', async () => {
    await dispatchAction('google_doc');
});

$('#sendOpenAI')?.addEventListener('click', async () => {
    await dispatchAction('openai_summary');
});

async function playElevenLabsText(text) {
    const data = await api('/api/elevenlabs-tts.php', { text });
    const player = $('#ttsPlayer') || document.createElement('audio');
    player.hidden = false;
    player.controls = true;
    player.src = data.audio.url;
    await player.play().catch(() => {});
    return data.audio;
}

$('#readWithElevenLabs')?.addEventListener('click', async () => {
    const text = ($('#editedOutput')?.value || $('#sessionPrompt')?.textContent || '').trim();
    if (!text) return alert('Nincs felolvasható szöveg.');
    try {
        await playElevenLabsText(text.slice(0, 4500));
    } catch (error) {
        alert(error.message);
    }
});

$('#archiveSession')?.addEventListener('click', async (event) => {
    const id = $('.session-detail')?.dataset.sessionId;
    const nextArchived = event.currentTarget.dataset.archived !== '1';
    await api('/api/session-archive.php', { id, archived: nextArchived });
    window.location.reload();
});

$('#copySessionPrompt')?.addEventListener('click', async () => {
    await navigator.clipboard.writeText($('#sessionPrompt')?.textContent || '');
    alert('ChatGPT prompt másolva.');
});

$('#archiveSearch')?.addEventListener('input', (event) => {
    const query = event.target.value.toLowerCase();
    $$('.session-card').forEach((card) => {
        card.style.display = card.textContent.toLowerCase().includes(query) ? '' : 'none';
    });
});

$$('.tabs button').forEach((button) => {
    button.addEventListener('click', () => {
        $$('.tabs button').forEach((b) => b.classList.remove('active'));
        button.classList.add('active');
    });
});

if (activeSessionId && $('#outputPreview')) {
    $('#outputPreview').textContent = 'Folytatás mód: az új rész ehhez a sessionhöz kerül.';
}

$('#settingsForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = {
        audio_provider: form.audio_provider.value,
        elevenlabs_api_key: form.elevenlabs_api_key.value,
        elevenlabs_voice_id: form.elevenlabs_voice_id.value,
        elevenlabs_agent_id: form.elevenlabs_agent_id.value,
        elevenlabs_voice_name: form.elevenlabs_voice_name.value,
        elevenlabs_tts_model_id: form.elevenlabs_tts_model_id.value,
        elevenlabs_stt_model_id: form.elevenlabs_stt_model_id.value,
        elevenlabs_language_code: form.elevenlabs_language_code.value,
        elevenlabs_output_format: form.elevenlabs_output_format.value,
        elevenlabs_stability: form.elevenlabs_stability.value,
        elevenlabs_similarity_boost: form.elevenlabs_similarity_boost.value,
        elevenlabs_diarize: form.elevenlabs_diarize.checked,
        openai_api_key: form.openai_api_key.value,
        openai_model: form.openai_model.value,
        openai_summary_model: form.openai_summary_model.value,
        public_base_url: form.public_base_url.value,
        email_enabled: form.email_enabled.checked,
        email_default_to: form.email_default_to.value,
        email_from: form.email_from.value,
        google_docs_enabled: form.google_docs_enabled.checked,
        google_docs_folder_id: form.google_docs_folder_id.value,
        digest_hour: form.digest_hour.value,
        speech_language: form.speech_language.value,
        notes_shortcut_url: form.notes_shortcut_url.value,
        drive_enabled: form.drive_enabled.checked,
        auto_generate_digest: form.auto_generate_digest.checked,
    };
    await api('/api/settings-save.php', payload);
    alert('Beállítások mentve.');
});

$('#checkElevenLabs')?.addEventListener('click', async () => {
    try {
        const data = await api('/api/elevenlabs-status.php');
        $('#elevenLabsStatus').textContent = JSON.stringify(data.elevenlabs, null, 2);
    } catch (error) {
        $('#elevenLabsStatus').textContent = error.message;
    }
});

$('#searchElevenVoices')?.addEventListener('click', async () => {
    const query = prompt('Milyen voice nevet keressek?', $('#settingsForm')?.elevenlabs_voice_name?.value || 'Adam');
    if (query === null) return;
    try {
        const response = await fetch(`/api/elevenlabs-voices.php?q=${encodeURIComponent(query)}`);
        const data = await response.json();
        if (!response.ok || data.ok === false) throw new Error(data.error || 'Voice keresési hiba');
        $('#elevenLabsStatus').textContent = JSON.stringify(data.voices.slice(0, 12), null, 2);
    } catch (error) {
        $('#elevenLabsStatus').textContent = error.message;
    }
});

$('#refreshSetup')?.addEventListener('click', async () => {
    const labels = {
        ok: 'rendben',
        paused: 'pihentetve',
        needs_attention: 'figyelmet kér',
        blocked: 'blokkolt',
    };
    const data = await api('/api/setup-status.php');
    const list = $('#setupList');
    if (!list) return;
    list.innerHTML = Object.entries(data.setup.checks).map(([, check]) => `
        <div class="setup-row setup-${check.status}">
            <strong>${escapeHtml(check.label)}</strong>
            <span>${escapeHtml(`${labels[check.status] || check.status} - ${check.detail}`)}</span>
        </div>
    `).join('');
});

$('#digestForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const date = event.currentTarget.date.value;
    const data = await api('/api/digest-generate.php', { date });
    $('#digestPreview').textContent = data.digest;
});

const outputsData = $('#outputsData');
if (outputsData) {
    let outputs = [];
    try { outputs = JSON.parse(outputsData.textContent || '[]'); } catch (_) {}
    $$('.version-button').forEach((button) => {
        button.addEventListener('click', () => {
            const output = outputs.find((item) => String(item.version) === button.dataset.version);
            if (!output) return;
            $('#editedOutput').value = output.markdown || '';
            $('#sessionPrompt').textContent = output.chatgpt_prompt || '';
        });
    });
}

$('#transcriptInput')?.addEventListener('input', (event) => {
    saveDraft();
});

restoreDraft();
