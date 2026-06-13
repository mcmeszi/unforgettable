<?php
require dirname(__DIR__) . '/app/bootstrap.php';
require_login();

$data = request_json();
$session = read_session((string) ($data['id'] ?? ''));
if (!$session) {
    json_response(['ok' => false, 'error' => 'Session nem található.'], 404);
}

$hadParts = count($session['parts'] ?? []) > 0;
$raw = trim((string) ($data['raw_transcript'] ?? ''));
if ($raw === '' && !$hadParts) {
    json_response(['ok' => false, 'error' => 'Üres sessiont nem zárok le. Mondj, írj vagy illessz be legalább egy transcript részletet.'], 422);
}

$part = append_session_part($session, $raw, (string) ($data['source'] ?? 'manual'));
if ($raw !== '' && important_command_detected($raw)) {
    mark_session_important($session);
}

$session['status'] = $hadParts ? 'continued' : 'closed';
$session['updated_at'] = now_iso();
$output = build_output($session);
$session['outputs'][] = $output;
$session['title'] = str_starts_with((string) $session['title'], 'Új gondolat - ')
    ? title_from_summary($output['summary'])
    : $session['title'];
$session['exports'] = write_exports($session);
file_put_contents(data_path('outputs/' . $session['id'] . '_v' . $output['version'] . '.md'), $output['markdown']);
write_session($session);
json_response(['ok' => true, 'session' => $session, 'output' => $output]);
