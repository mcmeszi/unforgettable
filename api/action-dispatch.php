<?php
require dirname(__DIR__) . '/app/bootstrap.php';
require dirname(__DIR__) . '/app/integrations.php';
require_login();

$data = request_json();
$session = read_session((string) ($data['id'] ?? ''));
if (!$session) {
    json_response(['ok' => false, 'error' => 'Session nem található.'], 404);
}

$action = (string) ($data['action'] ?? '');
try {
    if ($action === 'openai_summary') {
        $result = create_openai_session_summary($session);
    } elseif ($action === 'email') {
        $result = dispatch_session_email($session, trim((string) ($data['to'] ?? '')));
    } elseif ($action === 'google_doc') {
        $result = prepare_google_doc_export($session);
    } else {
        json_response(['ok' => false, 'error' => 'Ismeretlen akció.'], 400);
    }

    append_action_log((string) $session['id'], $action, $result);
    json_response(['ok' => true, 'action' => $action, 'result' => $result]);
} catch (Throwable $error) {
    $message = app_redact_secrets($error->getMessage());
    $result = [
        'status' => 'error',
        'message' => $message,
    ];
    append_action_log((string) $session['id'], $action ?: 'unknown', $result);
    json_response(['ok' => false, 'error' => $message, 'result' => $result], 500);
}
