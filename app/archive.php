<?php
require __DIR__ . '/bootstrap.php';
require_login();
$sessions = list_sessions();
if (!empty($_GET['important'])) {
    $sessions = array_values(array_filter($sessions, fn ($s) => !empty($s['important'])));
}
$range = (string) ($_GET['range'] ?? '');
$today = new DateTimeImmutable('today');
if ($range !== '') {
    $sessions = array_values(array_filter($sessions, function ($session) use ($range, $today): bool {
        try {
            $created = new DateTimeImmutable((string) ($session['created_at'] ?? ''));
        } catch (Throwable) {
            return false;
        }
        return match ($range) {
            'today' => $created >= $today,
            'yesterday' => $created >= $today->modify('-1 day') && $created < $today,
            'week' => $created >= $today->modify('-7 days'),
            'month' => $created >= $today->modify('first day of this month'),
            'archived' => !empty($session['archived']),
            default => true,
        };
    }));
}
?>
<!doctype html>
<html lang="hu">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Archívum - Unforgettable</title>
    <link rel="stylesheet" href="/assets/css/app.css">
</head>
<body>
<div class="shell">
    <?php include __DIR__ . '/nav.php'; ?>
    <main class="main">
        <header class="topbar"><div><h1>Archívum</h1><p>Dátum, cím, summary és fontos session szerint szűrhető.</p></div></header>
        <div class="filter-row">
            <a href="/app/archive.php?range=today">Ma</a>
            <a href="/app/archive.php?range=yesterday">Tegnap</a>
            <a href="/app/archive.php?range=week">Ezen a héten</a>
            <a href="/app/archive.php?range=month">Ebben a hónapban</a>
            <a href="/app/archive.php?important=1">Fontos</a>
            <a href="/app/archive.php?range=archived">Archivált</a>
        </div>
        <input class="search" id="archiveSearch" placeholder="Keresés címben vagy summaryban">
        <div class="session-list archive">
            <?php foreach ($sessions as $session): $latest = latest_output($session); ?>
                <a class="session-card" href="/app/session.php?id=<?= urlencode((string) $session['id']) ?>">
                    <time><?= htmlspecialchars(date('Y-m-d H:i', strtotime((string) $session['created_at']))) ?></time>
                    <strong><?= htmlspecialchars((string) $session['title']) ?></strong>
                    <span><?= htmlspecialchars((string) ($latest['summary'] ?? '')) ?></span>
                    <small><?= !empty($session['important']) ? 'Fontos · ' : '' ?><?= !empty($session['archived']) ? 'Archivált · ' : '' ?><?= count($session['parts'] ?? []) ?> rész · <?= count($session['research'] ?? []) ?> kutatás</small>
                </a>
            <?php endforeach; ?>
            <?php if (!$sessions): ?>
                <article class="session-card">
                    <time>-</time>
                    <strong>Nincs találat</strong>
                    <span>Ebben a szűrésben még nincs session.</span>
                    <small>Próbálj másik időszakot vagy keresést.</small>
                </article>
            <?php endif; ?>
        </div>
    </main>
</div>
<script src="/assets/js/app.js"></script>
</body>
</html>
