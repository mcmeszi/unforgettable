<?php
require dirname(__DIR__) . '/app/bootstrap.php';
require_login();

$data = request_json();
$title = trim((string) ($data['title'] ?? ''));
$session = new_session_array($title);
write_session($session);
json_response(['ok' => true, 'session' => $session]);
