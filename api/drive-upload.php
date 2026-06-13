<?php
require dirname(__DIR__) . '/app/bootstrap.php';
require dirname(__DIR__) . '/app/integrations.php';
require_login();

$data = request_json();
$session = read_session((string) ($data['id'] ?? ''));
if (!$session) {
    json_response(['ok' => false, 'error' => 'Session nem található.'], 404);
}
try {
    $session['drive'] = array_merge(upload_session_exports_to_drive($session), [
        'updated_at' => now_iso(),
    ]);
} catch (Throwable $error) {
    $session['drive'] = [
        'status' => 'error',
        'message' => app_redact_secrets($error->getMessage()),
        'updated_at' => now_iso(),
    ];
}
write_session($session);
json_response(['ok' => true, 'drive' => $session['drive']]);
