<?php

declare(strict_types=1);

require dirname(__DIR__) . '/app/bootstrap.php';

$date = date('Y-m-d', strtotime('-1 day'));
$quiet = false;

foreach (array_slice($argv, 1) as $index => $arg) {
    if ($arg === '--quiet') {
        $quiet = true;
        continue;
    }
    if ($arg === '--date' && isset($argv[$index + 2])) {
        $date = (string) $argv[$index + 2];
        continue;
    }
    if (str_starts_with($arg, '--date=')) {
        $date = substr($arg, 7);
    }
}

$digest = build_daily_digest($date);

if (!$quiet) {
    echo "DIGEST_DATE=" . $digest['date'] . PHP_EOL;
    echo "SESSION_COUNT=" . $digest['session_count'] . PHP_EOL;
    echo "DIGEST_FILE=" . $digest['file'] . PHP_EOL;
}
