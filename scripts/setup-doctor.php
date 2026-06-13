<?php

declare(strict_types=1);

require dirname(__DIR__) . '/app/bootstrap.php';

$status = app_setup_status();
$labels = [
    'ok' => 'OK',
    'paused' => 'PAUSED',
    'needs_attention' => 'CHECK',
    'blocked' => 'BLOCKED',
];

echo "Unforgettable setup doctor\n";
echo "Generated: " . $status['generated_at'] . "\n\n";

foreach ($status['checks'] as $check) {
    $state = (string) ($check['status'] ?? 'needs_attention');
    echo '[' . ($labels[$state] ?? strtoupper($state)) . '] '
        . (string) ($check['label'] ?? '')
        . ' - '
        . (string) ($check['detail'] ?? '')
        . PHP_EOL;
}

echo "\nSummary: ";
foreach ($status['counts'] as $key => $count) {
    echo ($labels[$key] ?? strtoupper($key)) . '=' . $count . ' ';
}
echo PHP_EOL;

exit(($status['counts']['blocked'] ?? 0) > 0 ? 1 : 0);
