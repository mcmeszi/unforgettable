<?php
require dirname(__DIR__) . '/app/bootstrap.php';
require_login();

$data = request_json();
$session = read_session((string) ($data['id'] ?? ''));
if (!$session) {
    json_response(['ok' => false, 'error' => 'Session nem található.'], 404);
}

$raw = trim((string) ($data['raw_transcript'] ?? ''));
if (!empty($data['append_part'])) {
    if ($raw === '') {
        json_response(['ok' => false, 'error' => 'Üres transcript nem menthető új részként.'], 422);
    }
    append_session_part($session, $raw, (string) ($data['source'] ?? 'manual'));
}

if (!empty($data['important']) || important_command_detected($raw)) {
    mark_session_important($session);
}

if (array_key_exists('title', $data)) {
    $title = trim((string) $data['title']);
    if ($title !== '') {
        $session['title'] = app_substr($title, 0, 120);
    }
}

if (array_key_exists('user_edited_output', $data)) {
    $session['user_edited_output'] = [
        'created_at' => now_iso(),
        'content' => (string) $data['user_edited_output'],
    ];
}

if (array_key_exists('archived', $data)) {
    $session['archived'] = !empty($data['archived']);
    $session['status'] = $session['archived'] ? 'archived' : 'closed';
}

if (!empty($data['status'])) {
    $session['status'] = normalize_session_status((string) $data['status'], $session);
}
$session['updated_at'] = now_iso();
write_session($session);
json_response(['ok' => true, 'session' => $session]);
