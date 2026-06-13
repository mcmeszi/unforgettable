<?php
require __DIR__ . '/bootstrap.php';
require_login();

$status = app_setup_status();
$statusLabels = [
    'ok' => 'rendben',
    'paused' => 'pihentetve',
    'needs_attention' => 'figyelmet kér',
    'blocked' => 'blokkolt',
];
?>
<!doctype html>
<html lang="hu">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Setup - Unforgettable</title>
    <link rel="stylesheet" href="/assets/css/app.css">
</head>
<body>
<div class="shell no-side">
    <?php include __DIR__ . '/nav.php'; ?>
    <main class="main">
        <header class="topbar">
            <div>
                <h1>Setup</h1>
                <p>Integrációk és futtatási feltételek állapota, titkok megjelenítése nélkül.</p>
            </div>
            <div class="top-actions">
                <button id="refreshSetup">Frissítés</button>
            </div>
        </header>
        <section class="meta-strip">
            <?php foreach ($status['counts'] as $key => $count): ?>
                <div>
                    <strong><?= htmlspecialchars($statusLabels[$key] ?? $key) ?></strong>
                    <span><?= htmlspecialchars((string) $count) ?></span>
                </div>
            <?php endforeach; ?>
        </section>
        <section class="settings-list setup-list" id="setupList">
            <?php foreach ($status['checks'] as $key => $check): ?>
                <div class="setup-row setup-<?= htmlspecialchars((string) $check['status']) ?>">
                    <strong><?= htmlspecialchars((string) $check['label']) ?></strong>
                    <span><?= htmlspecialchars(($statusLabels[$check['status']] ?? $check['status']) . ' - ' . (string) $check['detail']) ?></span>
                </div>
            <?php endforeach; ?>
        </section>
        <section class="tool-panel">
            <h2>Hasznos parancsok</h2>
            <pre>php scripts\setup-doctor.php
php scripts\setup-elevenlabs-agent.php
php scripts\cron-digest.php --date <?= htmlspecialchars(date('Y-m-d', strtotime('-1 day'))) ?></pre>
        </section>
    </main>
</div>
<script src="/assets/js/app.js"></script>
</body>
</html>
