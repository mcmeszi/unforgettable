<?php
require __DIR__ . '/bootstrap.php';
require_login();

$digestFiles = glob(data_path('digests/*.md')) ?: [];
rsort($digestFiles);
?>
<!doctype html>
<html lang="hu">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Digestek - Unforgettable</title>
    <link rel="stylesheet" href="/assets/css/app.css">
</head>
<body>
<div class="shell no-side">
    <?php include __DIR__ . '/nav.php'; ?>
    <main class="main">
        <header class="topbar">
            <div>
                <h1>Reggeli digest</h1>
                <p>Az előző napi sessionök áttekintése, exportlinkekkel és fontos jelölésekkel.</p>
            </div>
        </header>
        <form class="digest-form" id="digestForm">
            <input name="date" type="date" value="<?= htmlspecialchars(date('Y-m-d', strtotime('-1 day'))) ?>">
            <button class="primary" type="submit">Digest generálása</button>
        </form>
        <section class="digest-preview">
            <h2>Előnézet</h2>
            <pre id="digestPreview">Válassz dátumot és generálj digestet.</pre>
        </section>
        <section>
            <h2>Korábbi digestek</h2>
            <div class="session-list">
                <?php foreach ($digestFiles as $file): ?>
                    <article class="session-card">
                        <time><?= htmlspecialchars(basename($file, '.md')) ?></time>
                        <strong>Reggeli Digest</strong>
                        <span><?= htmlspecialchars(trim((string) strtok((string) file_get_contents($file), "\n")) ?: 'Digest') ?></span>
                        <small><?= htmlspecialchars(date('Y-m-d H:i', filemtime($file))) ?></small>
                    </article>
                <?php endforeach; ?>
            </div>
        </section>
    </main>
</div>
<script src="/assets/js/app.js"></script>
</body>
</html>
