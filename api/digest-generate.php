<?php
require dirname(__DIR__) . '/app/bootstrap.php';
require_login();

$input = request_json();
$date = (string) ($_GET['date'] ?? ($input['date'] ?? date('Y-m-d', strtotime('-1 day'))));
$digest = build_daily_digest($date);

json_response([
    'ok' => true,
    'date' => $digest['date'],
    'session_count' => $digest['session_count'],
    'file' => $digest['file'],
    'digest' => $digest['digest'],
]);
