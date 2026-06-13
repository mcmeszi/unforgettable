<?php
require __DIR__ . '/bootstrap.php';
require_login();
$sessions = list_sessions();
$continueId = preg_replace('/[^a-zA-Z0-9_-]/', '', (string) ($_GET['continue'] ?? ''));
$continueSession = $continueId ? read_session($continueId) : null;
$settings = app_settings();
?>
<!doctype html>
<html lang="hu">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Unforgettable</title>
    <link rel="stylesheet" href="/assets/css/app.css">
</head>
<body>
<div class="shell">
    <?php include __DIR__ . '/nav.php'; ?>
    <main class="main">
        <header class="topbar">
            <div>
                <h1><?= $continueSession ? 'Folytatás: ' . htmlspecialchars((string) $continueSession['title']) : 'Ma mit ne veszítsünk el?' ?></h1>
                <p><?= $continueSession ? 'Az új rész ugyanebbe a sessionbe kerül, a régi output megmarad verzióként.' : 'Indíts rögzítést kategóriaválasztás nélkül.' ?></p>
            </div>
            <button class="primary" id="newSession">Új session</button>
        </header>
        <section class="recorder" data-session-id="<?= htmlspecialchars($continueId) ?>" data-speech-language="<?= htmlspecialchars((string) $settings['speech_language']) ?>" data-audio-provider="<?= htmlspecialchars((string) $settings['audio_provider']) ?>">
            <div class="record-orb" id="recordButton"><span></span></div>
            <div class="timer" id="timer">00:00:00</div>
            <div class="control-row">
                <button id="importantBtn">Tuti mentsd el</button>
                <button id="readBackBtn">Olvasd vissza</button>
                <button id="researchBtn">Nézz utána</button>
                <button id="stopBtn">Leállítás</button>
            </div>
            <div class="provider-status" id="providerStatus">
                <?= $settings['audio_provider'] === 'elevenlabs' ? 'ElevenLabs STT/TTS mód' : 'Böngészős beszédfelismerés mód' ?>
            </div>
            <textarea id="transcriptInput" placeholder="A beszédfelismerés ide kerül. Ha a böngésző nem támogatja, ide írhatod vagy bemásolhatod a transcriptet."></textarea>
        </section>
        <section class="timeline">
            <div class="section-head">
                <h2>Időalapú archívum</h2>
                <a href="/app/archive.php">Teljes archívum</a>
            </div>
            <div class="session-list">
                <?php foreach ($sessions as $session): ?>
                    <?php $latest = latest_output($session); ?>
                    <a class="session-card" href="/app/session.php?id=<?= urlencode((string) $session['id']) ?>">
                        <time><?= htmlspecialchars(date('H:i', strtotime((string) $session['created_at']))) ?></time>
                        <strong><?= htmlspecialchars((string) ($session['title'] ?? 'Névtelen session')) ?></strong>
                        <span><?= htmlspecialchars((string) ($latest['summary'] ?? 'Nincs még summary.')) ?></span>
                        <small><?= !empty($session['important']) ? 'Fontos session · ' : '' ?><?= count($session['parts'] ?? []) ?> rész · <?= htmlspecialchars((string) $session['status']) ?></small>
                    </a>
                <?php endforeach; ?>
            </div>
        </section>
    </main>
    <aside class="side-panel">
        <div class="tabs">
            <button class="active" data-tab="raw">Nyers</button>
            <button data-tab="clean">Tisztított</button>
            <button data-tab="final">Final</button>
        </div>
        <pre id="outputPreview">Indíts vagy nyiss meg egy sessiont.</pre>
        <div class="export-grid">
            <button data-export="pdf">PDF</button>
            <button data-export="markdown">MD</button>
            <button data-export="txt">TXT</button>
            <button data-export="json">JSON</button>
            <button id="copyChatGPT">ChatGPT</button>
        </div>
    </aside>
</div>
<script src="/assets/js/app.js"></script>
</body>
</html>
