<?php
require __DIR__ . '/bootstrap.php';
require_login();
$settings = app_settings();
?>
<!doctype html>
<html lang="hu">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Beállítások - Unforgettable</title>
    <link rel="stylesheet" href="/assets/css/app.css">
</head>
<body>
<div class="shell">
    <?php include __DIR__ . '/nav.php'; ?>
    <main class="main">
        <header class="topbar"><div><h1>Beállítások</h1><p>Kulcsok backend oldalon, frontendbe nem kerülnek.</p></div></header>
        <form class="settings-form" id="settingsForm">
            <label>
                <span>Audio provider</span>
                <select name="audio_provider">
                    <option value="browser" <?= $settings['audio_provider'] === 'browser' ? 'selected' : '' ?>>Böngésző fallback</option>
                    <option value="elevenlabs" <?= $settings['audio_provider'] === 'elevenlabs' ? 'selected' : '' ?>>ElevenLabs STT/TTS</option>
                </select>
            </label>
            <label>
                <span>ElevenLabs API key</span>
                <input name="elevenlabs_api_key" type="password" placeholder="<?= $settings['elevenlabs_api_key'] ? 'Beállítva - üresen hagyva megmarad' : 'xi-api-key' ?>">
            </label>
            <label>
                <span>ElevenLabs voice ID</span>
                <input name="elevenlabs_voice_id" value="<?= htmlspecialchars((string) $settings['elevenlabs_voice_id']) ?>">
            </label>
            <label>
                <span>ElevenLabs agent ID</span>
                <input name="elevenlabs_agent_id" value="<?= htmlspecialchars((string) $settings['elevenlabs_agent_id']) ?>">
            </label>
            <label>
                <span>Voice név</span>
                <input name="elevenlabs_voice_name" value="<?= htmlspecialchars((string) $settings['elevenlabs_voice_name']) ?>">
            </label>
            <label>
                <span>TTS model</span>
                <input name="elevenlabs_tts_model_id" value="<?= htmlspecialchars((string) $settings['elevenlabs_tts_model_id']) ?>">
            </label>
            <label>
                <span>STT model</span>
                <input name="elevenlabs_stt_model_id" value="<?= htmlspecialchars((string) $settings['elevenlabs_stt_model_id']) ?>">
            </label>
            <label>
                <span>ElevenLabs nyelv</span>
                <input name="elevenlabs_language_code" value="<?= htmlspecialchars((string) $settings['elevenlabs_language_code']) ?>">
            </label>
            <label>
                <span>Output formátum</span>
                <input name="elevenlabs_output_format" value="<?= htmlspecialchars((string) $settings['elevenlabs_output_format']) ?>">
            </label>
            <label>
                <span>Stability</span>
                <input name="elevenlabs_stability" type="number" min="0" max="1" step="0.05" value="<?= htmlspecialchars((string) $settings['elevenlabs_stability']) ?>">
            </label>
            <label>
                <span>Similarity boost</span>
                <input name="elevenlabs_similarity_boost" type="number" min="0" max="1" step="0.05" value="<?= htmlspecialchars((string) $settings['elevenlabs_similarity_boost']) ?>">
            </label>
            <label class="check-row">
                <input name="elevenlabs_diarize" type="checkbox" <?= !empty($settings['elevenlabs_diarize']) ? 'checked' : '' ?>>
                <span>Beszélőfelismerés STT-nél</span>
            </label>
            <label>
                <span>OpenAI API key</span>
                <input name="openai_api_key" type="password" placeholder="<?= $settings['openai_api_key'] ? 'Beállítva - üresen hagyva megmarad' : 'sk-...' ?>">
            </label>
            <label>
                <span>OpenAI alap modell</span>
                <input name="openai_model" value="<?= htmlspecialchars((string) $settings['openai_model']) ?>">
            </label>
            <label>
                <span>OpenAI summary model</span>
                <input name="openai_summary_model" value="<?= htmlspecialchars((string) $settings['openai_summary_model']) ?>">
            </label>
            <label>
                <span>Publikus app URL</span>
                <input name="public_base_url" value="<?= htmlspecialchars((string) $settings['public_base_url']) ?>" placeholder="https://your-domain.example">
            </label>
            <label class="check-row">
                <input name="email_enabled" type="checkbox" <?= !empty($settings['email_enabled']) ? 'checked' : '' ?>>
                <span>Email küldés engedélyezve</span>
            </label>
            <label>
                <span>Alapértelmezett címzett email</span>
                <input name="email_default_to" type="email" value="<?= htmlspecialchars((string) $settings['email_default_to']) ?>">
            </label>
            <label>
                <span>Küldő email</span>
                <input name="email_from" type="email" value="<?= htmlspecialchars((string) $settings['email_from']) ?>">
            </label>
            <label class="check-row">
                <input name="google_docs_enabled" type="checkbox" <?= !empty($settings['google_docs_enabled']) ? 'checked' : '' ?>>
                <span>Google Docs adapter engedélyezve</span>
            </label>
            <label>
                <span>Google Docs folder ID</span>
                <input name="google_docs_folder_id" value="<?= htmlspecialchars((string) $settings['google_docs_folder_id']) ?>">
            </label>
            <label>
                <span>Digest idő</span>
                <input name="digest_hour" type="time" value="<?= htmlspecialchars((string) $settings['digest_hour']) ?>">
            </label>
            <label>
                <span>Beszédfelismerés nyelve</span>
                <input name="speech_language" value="<?= htmlspecialchars((string) $settings['speech_language']) ?>">
            </label>
            <label>
                <span>iOS Shortcut URL</span>
                <input name="notes_shortcut_url" value="<?= htmlspecialchars((string) $settings['notes_shortcut_url']) ?>">
            </label>
            <label class="check-row">
                <input name="drive_enabled" type="checkbox" <?= !empty($settings['drive_enabled']) ? 'checked' : '' ?>>
                <span>Drive export bekapcsolva</span>
            </label>
            <label class="check-row">
                <input name="auto_generate_digest" type="checkbox" <?= !empty($settings['auto_generate_digest']) ? 'checked' : '' ?>>
                <span>Digest automatikus előkészítése</span>
            </label>
            <button class="primary" type="submit">Beállítások mentése</button>
        </form>
        <section class="tool-panel">
            <div class="control-row">
                <button id="checkElevenLabs">ElevenLabs státusz</button>
                <button id="searchElevenVoices">Voice keresés</button>
            </div>
            <pre id="elevenLabsStatus">A státuszellenőrzés nem fut automatikusan, hogy ne legyen felesleges API-hívás.</pre>
        </section>
        <section class="settings-list">
            <div><strong>OpenAI API</strong><span><?= $settings['openai_api_key'] ? 'konfigurálva' : 'nincs bekötve' ?></span></div>
            <div><strong>Search API</strong><span><?= $secrets['search_api_key'] ? 'konfigurálva' : 'stub mód' ?></span></div>
            <div><strong>ElevenLabs</strong><span><?= $settings['elevenlabs_api_key'] ? 'konfigurálva' : 'nincs bekötve' ?></span></div>
            <div><strong>ElevenLabs agent</strong><span><?= $settings['elevenlabs_agent_id'] ? htmlspecialchars((string) $settings['elevenlabs_agent_id']) : 'nincs létrehozva' ?></span></div>
            <div><strong>ElevenLabs agent secret</strong><span><?= $settings['elevenlabs_agent_tool_secret'] ? 'konfigurálva' : 'nincs bekötve' ?></span></div>
            <div><strong>ElevenLabs webhook secret</strong><span><?= $settings['elevenlabs_webhook_secret'] ? 'konfigurálva' : 'nincs bekötve' ?></span></div>
            <div><strong>Publikus app URL</strong><span><?= $settings['public_base_url'] ? htmlspecialchars((string) $settings['public_base_url']) : 'nincs beállítva' ?></span></div>
            <div><strong>Email</strong><span><?= !empty($settings['email_enabled']) ? 'küldés bekapcsolva' : 'előkészítő mód' ?></span></div>
            <div><strong>Google Docs</strong><span><?= !empty($settings['google_integration_paused']) ? 'pihentetve' : (!empty($settings['google_docs_enabled']) ? (google_docs_auth_configured() ? 'adapter aktív' : 'adapterhez hiányzik OAuth/service account') : 'előkészítő mód') ?></span></div>
            <div><strong>Drive export</strong><span><?= !empty($settings['google_integration_paused']) ? 'pihentetve' : (!empty($settings['drive_enabled']) ? 'bekapcsolva' : 'stub mód') ?></span></div>
        </section>
    </main>
</div>
<script src="/assets/js/app.js"></script>
</body>
</html>
