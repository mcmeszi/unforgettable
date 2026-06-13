<?php
require dirname(__DIR__) . '/app/bootstrap.php';
require_login();

$data = request_json();
$session = read_session((string) ($data['id'] ?? ''));
if (!$session) {
    json_response(['ok' => false, 'error' => 'Session nem található.'], 404);
}

$archived = !empty($data['archived']);
$session['archived'] = $archived;
$session['status'] = $archived ? 'archived' : (count($session['parts'] ?? []) > 1 ? 'continued' : 'closed');
$session['updated_at'] = now_iso();
write_session($session);

json_response(['ok' => true, 'session' => $session]);
