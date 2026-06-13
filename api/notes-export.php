<?php
require dirname(__DIR__) . '/app/bootstrap.php';
require_login();

$data = request_json();
$session = read_session((string) ($data['id'] ?? ''));
if (!$session) {
    json_response(['ok' => false, 'error' => 'Session nem található.'], 404);
}
$latest = latest_output($session);
$edited = $session['user_edited_output']['content'] ?? null;
$content = "# Unforgettable - " . date('Y-m-d - H:i', strtotime((string) $session['created_at'])) . "\n\n"
    . "## Rövid summary\n" . (string) ($latest['summary'] ?? '') . "\n\n"
    . "## Final output\n" . (string) ($edited ?? ($latest['markdown'] ?? '')) . "\n\n"
    . "## Fontos session\n" . (!empty($session['important']) ? 'igen' : 'nem') . "\n\n";
file_put_contents(data_path('exports/' . $session['id'] . '_notes.md'), $content);
$settings = app_settings();
$session['notes'] = ['status' => 'prepared', 'shortcut_url' => $settings['notes_shortcut_url'], 'updated_at' => now_iso()];
write_session($session);
json_response(['ok' => true, 'notes' => $session['notes'], 'content' => $content]);
