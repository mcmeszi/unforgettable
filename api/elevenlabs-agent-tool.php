<?php
require dirname(__DIR__) . '/app/bootstrap.php';
require dirname(__DIR__) . '/app/integrations.php';
require dirname(__DIR__) . '/app/agent-tools.php';

require_elevenlabs_agent_auth();

$data = request_json();
$parameters = isset($data['parameters']) && is_array($data['parameters']) ? $data['parameters'] : [];
$toolName = (string) ($data['tool_name'] ?? $data['name'] ?? '');
$payload = array_merge($data, $parameters);
$action = (string) ($payload['action'] ?? $toolName);
$result = ['status' => 'unknown_action'];

try {
    if ($action === 'search_archive') {
        $result = [
            'status' => 'ok',
            'results' => search_unforgettable_archive(
                (string) ($payload['query'] ?? ''),
                (int) ($payload['limit'] ?? 5)
            ),
        ];
    } elseif ($action === 'get_session') {
        $result = get_agent_session((string) ($payload['session_id'] ?? ''));
    } elseif ($action === 'save_memory') {
        $result = save_agent_memory(
            (string) ($payload['text'] ?? ''),
            (string) ($payload['title'] ?? ''),
            !empty($payload['important'])
        );
    } elseif ($action === 'append_memory') {
        $result = append_agent_memory(
            (string) ($payload['session_id'] ?? ''),
            (string) ($payload['text'] ?? ''),
            !empty($payload['important'])
        );
    } elseif ($action === 'prepare_email') {
        $session = read_session((string) ($payload['session_id'] ?? ''));
        $result = $session
            ? dispatch_session_email($session, trim((string) ($payload['to'] ?? '')))
            : ['status' => 'not_found', 'message' => 'Session nem található.'];
    } elseif ($action === 'prepare_google_doc') {
        $session = read_session((string) ($payload['session_id'] ?? ''));
        $result = $session
            ? prepare_google_doc_export($session)
            : ['status' => 'not_found', 'message' => 'Session nem található.'];
    } elseif ($action === 'send_openai_summary') {
        $session = read_session((string) ($payload['session_id'] ?? ''));
        $result = $session
            ? create_openai_session_summary($session)
            : ['status' => 'not_found', 'message' => 'Session nem található.'];
    } else {
        json_response(['ok' => false, 'error' => 'Ismeretlen ElevenLabs agent action.'], 400);
    }

    append_action_log((string) ($payload['session_id'] ?? ($result['session_id'] ?? 'agent_gateway')), 'elevenlabs_agent_' . $action, $result);
    json_response(['ok' => true, 'action' => $action, 'result' => $result]);
} catch (Throwable $error) {
    $message = app_redact_secrets($error->getMessage());
    append_action_log((string) ($payload['session_id'] ?? 'agent_gateway'), 'elevenlabs_agent_' . ($action ?: 'unknown'), [
        'status' => 'error',
        'message' => $message,
    ]);
    json_response(['ok' => false, 'error' => $message], 500);
}
