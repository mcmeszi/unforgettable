<?php
require __DIR__ . '/bootstrap.php';
require_login();
$settings = app_settings();
$session = read_session((string) ($_GET['id'] ?? ''));
if (!$session) {
    http_response_code(404);
    echo 'Session nem található.';
    exit;
}
$latest = latest_output($session);
$editedOutput = (string) ($session['user_edited_output']['content'] ?? ($latest['markdown'] ?? ''));
?>
<!doctype html>
<html lang="hu">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title><?= htmlspecialchars((string) $session['title']) ?> - Unforgettable</title>
    <link rel="stylesheet" href="/assets/css/app.css">
</head>
<body>
<div class="shell">
    <?php include __DIR__ . '/nav.php'; ?>
    <main class="main session-detail" data-session-id="<?= htmlspecialchars((string) $session['id']) ?>">
        <header class="topbar">
            <div>
                <h1><?= htmlspecialchars((string) $session['title']) ?></h1>
                <p><?= htmlspecialchars(date('Y-m-d H:i', strtotime((string) $session['created_at']))) ?> · <?= htmlspecialchars((string) $session['status']) ?> · <?= count($session['parts'] ?? []) ?> rész · <?= count($session['outputs'] ?? []) ?> output</p>
            </div>
            <div class="top-actions">
                <button id="generateOutput">Output frissítés</button>
                <button class="primary" id="continueSession">Folytatás</button>
            </div>
        </header>
        <section class="meta-strip">
            <div><strong>Státusz</strong><span><?= htmlspecialchars((string) $session['status']) ?></span></div>
            <div><strong>Fontos</strong><span><?= !empty($session['important']) ? 'igen' : 'nem' ?></span></div>
            <div><strong>Drive</strong><span><?= htmlspecialchars((string) ($session['drive']['status'] ?? 'none')) ?></span></div>
            <div><strong>Notes</strong><span><?= htmlspecialchars((string) ($session['notes']['status'] ?? 'none')) ?></span></div>
            <div><strong>Prioritás</strong><span><?= htmlspecialchars((string) ($session['archive_priority'] ?? 'normal')) ?></span></div>
        </section>
        <section>
            <div class="section-head">
                <h2>Session részek</h2>
                <button id="archiveSession" data-archived="<?= !empty($session['archived']) ? '1' : '0' ?>"><?= !empty($session['archived']) ? 'Visszaállítás' : 'Archiválás' ?></button>
            </div>
            <div class="part-list">
                <?php foreach (($session['parts'] ?? []) as $part): ?>
                    <article>
                        <strong>Part <?= htmlspecialchars((string) ($part['part_number'] ?? '')) ?></strong>
                        <span><?= htmlspecialchars(date('Y-m-d H:i', strtotime((string) $part['created_at']))) ?> · <?= htmlspecialchars((string) ($part['source'] ?? 'manual')) ?></span>
                    </article>
                <?php endforeach; ?>
            </div>
        </section>
        <div class="detail-grid">
            <section>
                <h2>Nyers transcript</h2>
                <pre><?= htmlspecialchars(implode("\n\n", array_map(fn ($p) => (string) ($p['raw_transcript'] ?? ''), $session['parts'] ?? []))) ?></pre>
            </section>
            <section>
                <h2>Tisztított transcript</h2>
                <pre><?= htmlspecialchars(implode("\n\n", array_map(fn ($p) => (string) ($p['clean_transcript'] ?? ''), $session['parts'] ?? []))) ?></pre>
            </section>
        </div>
        <section>
            <h2>Final output</h2>
            <textarea id="editedOutput"><?= htmlspecialchars($editedOutput) ?></textarea>
            <div class="control-row">
                <button id="saveEdited">Mentés külön rétegként</button>
                <button id="generateDigest">Reggeli digest</button>
                <button id="readWithElevenLabs">ElevenLabs felolvasás</button>
                <button id="sendNotes">Küldés iOS Jegyzetekbe</button>
                <button id="sendDrive" <?= !empty($settings['google_integration_paused']) ? 'disabled title="Google/Drive integráció pihentetve"' : '' ?>>Drive export</button>
                <button id="sendEmail">Email küldés</button>
                <button id="createGoogleDoc" <?= !empty($settings['google_integration_paused']) ? 'disabled title="Google/Drive integráció pihentetve"' : '' ?>>Google Docs</button>
                <button id="sendOpenAI">OpenAI summary</button>
            </div>
            <pre id="actionStatus" class="status-box">Az integrációk csak gombnyomásra futnak.</pre>
            <audio id="ttsPlayer" controls hidden></audio>
        </section>
    </main>
    <aside class="side-panel">
        <h2>Export</h2>
        <div class="export-grid">
            <?php foreach (($session['exports'] ?? []) as $type => $url): ?>
                <a href="<?= htmlspecialchars((string) $url) ?>"><?= strtoupper(htmlspecialchars((string) $type)) ?></a>
            <?php endforeach; ?>
        </div>
        <button id="copySessionPrompt">Másolás ChatGPT-be</button>
        <pre id="sessionPrompt"><?= htmlspecialchars((string) ($latest['chatgpt_prompt'] ?? '')) ?></pre>
        <h2>Output verziók</h2>
        <div class="version-list">
            <?php foreach (array_reverse($session['outputs'] ?? []) as $output): ?>
                <button class="version-button" data-version="<?= htmlspecialchars((string) $output['version']) ?>">v<?= htmlspecialchars((string) $output['version']) ?> · <?= htmlspecialchars(date('H:i', strtotime((string) $output['created_at']))) ?></button>
            <?php endforeach; ?>
        </div>
        <h2>Kutatások</h2>
        <div class="research-list">
            <?php foreach (($session['research'] ?? []) as $research): ?>
                <article>
                    <strong><?= htmlspecialchars((string) $research['query']) ?></strong>
                    <span><?= count($research['results'] ?? []) ?> találat</span>
                </article>
            <?php endforeach; ?>
        </div>
    </aside>
</div>
<script type="application/json" id="outputsData"><?= json_encode($session['outputs'] ?? [], JSON_UNESCAPED_UNICODE | JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT) ?></script>
<script src="/assets/js/app.js"></script>
</body>
</html>
