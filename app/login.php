<?php
require __DIR__ . '/bootstrap.php';

$error = '';
$stateFile = data_path('settings/login-rate.json');
$state = is_file($stateFile) ? json_decode((string) file_get_contents($stateFile), true) : ['failures' => 0, 'locked_until' => 0];

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $now = time();
    if (($state['locked_until'] ?? 0) > $now) {
        $error = 'Túl sok próbálkozás. Próbáld újra pár perc múlva.';
    } elseif (password_verify((string) ($_POST['password'] ?? ''), (string) $secrets['password_hash'])) {
        $_SESSION['logged_in'] = true;
        file_put_contents($stateFile, json_encode(['failures' => 0, 'locked_until' => 0]));
        header('Location: /app/index.php');
        exit;
    } else {
        $failures = (int) ($state['failures'] ?? 0) + 1;
        $state = ['failures' => $failures, 'locked_until' => $failures >= 5 ? $now + 600 : 0];
        file_put_contents($stateFile, json_encode($state));
        $error = 'Hibás jelszó.';
    }
}
?>
<!doctype html>
<html lang="hu">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Unforgettable - belépés</title>
    <link rel="stylesheet" href="/assets/css/app.css">
</head>
<body class="login-screen">
    <main class="login-panel">
        <div class="brand-mark">U</div>
        <h1>Unforgettable</h1>
        <p>Személyes kreatív memória.</p>
        <?php if ($error): ?><div class="alert"><?= htmlspecialchars($error) ?></div><?php endif; ?>
        <form method="post">
            <label for="password">Jelszó</label>
            <input id="password" name="password" type="password" autofocus required>
            <button type="submit">Belépés</button>
        </form>
    </main>
</body>
</html>
