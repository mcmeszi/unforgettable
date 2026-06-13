<?php
require dirname(__DIR__) . '/app/bootstrap.php';
require_login();

$data = request_json();
$session = read_session((string) ($data['id'] ?? ''));
if (!$session) {
    json_response(['ok' => false, 'error' => 'Session nem található.'], 404);
}
if (!session_has_parts($session)) {
    json_response(['ok' => false, 'error' => 'Nincs transcript rész, ezért még nem lehet outputot generálni.'], 422);
}
$output = build_output($session);
$session['outputs'][] = $output;
$session['exports'] = write_exports($session);
$session['status'] = ($session['status'] === 'archived') ? 'archived' : (count($session['parts'] ?? []) > 1 ? 'continued' : 'closed');
$session['updated_at'] = now_iso();
file_put_contents(data_path('outputs/' . $session['id'] . '_v' . $output['version'] . '.md'), $output['markdown']);
write_session($session);
json_response(['ok' => true, 'output' => $output, 'exports' => $session['exports']]);
