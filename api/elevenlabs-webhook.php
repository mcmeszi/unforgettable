<?php
require dirname(__DIR__) . '/app/bootstrap.php';
require dirname(__DIR__) . '/app/integrations.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    json_response(['ok' => false, 'error' => 'Csak POST webhook támogatott.'], 405);
}

$raw = file_get_contents('php://input') ?: '';
$secret = elevenlabs_webhook_secret();
if ($secret === '') {
    json_response(['ok' => false, 'error' => 'ElevenLabs webhook secret nincs beállítva.'], 503);
}

if (!verify_elevenlabs_webhook($raw, $secret)) {
    json_response(['ok' => false, 'error' => 'Érvénytelen webhook aláírás vagy secret.'], 401);
}

$payload = json_decode($raw, true);
if (!is_array($payload)) {
    json_response(['ok' => false, 'error' => 'Érvénytelen JSON payload.'], 400);
}

ensure_storage();
$eventId = safe_id((string) ($payload['event_id'] ?? $payload['id'] ?? make_id('elevenlabs_webhook')));
$eventFile = data_path('actions/' . $eventId . '_raw_webhook.json');
file_put_contents($eventFile, json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT), LOCK_EX);

$text = extract_webhook_transcript($payload);
$sessionResult = null;
if (trim($text) !== '') {
    $session = new_session_array('ElevenLabs call - ' . date('H:i'));
    $session['source'] = 'elevenlabs_webhook';
    $session['elevenlabs'] = [
        'event_id' => $eventId,
        'conversation_id' => (string) ($payload['conversation_id'] ?? ($payload['data']['conversation_id'] ?? '')),
        'agent_id' => (string) ($payload['agent_id'] ?? ($payload['data']['agent_id'] ?? '')),
    ];
    append_session_part($session, $text, 'elevenlabs_webhook');
    $session['status'] = 'closed';
    $session['updated_at'] = now_iso();
    $output = build_output($session);
    $session['outputs'][] = $output;
    $session['title'] = title_from_summary($output['summary']);
    $session['exports'] = write_exports($session);
    file_put_contents(data_path('outputs/' . $session['id'] . '_v' . $output['version'] . '.md'), $output['markdown']);
    write_session($session);
    $sessionResult = [
        'session_id' => $session['id'],
        'title' => $session['title'],
        'summary' => $output['summary'],
    ];
    append_action_log((string) $session['id'], 'elevenlabs_post_call_webhook', [
        'status' => 'saved',
        'event_id' => $eventId,
        'raw_file' => $eventFile,
    ]);
}

json_response([
    'ok' => true,
    'event_id' => $eventId,
    'raw_file' => $eventFile,
    'session' => $sessionResult,
]);

function verify_elevenlabs_webhook(string $raw, string $secret): bool
{
    $custom = request_header('X-Unforgettable-Webhook-Secret');
    if ($custom !== '' && hash_equals($secret, $custom)) {
        return true;
    }

    $signature = request_header('ElevenLabs-Signature');
    if ($signature === '') {
        return false;
    }

    $timestamp = '';
    $provided = '';
    foreach (explode(',', $signature) as $part) {
        [$key, $value] = array_pad(explode('=', trim($part), 2), 2, '');
        if ($key === 't') {
            $timestamp = $value;
        } elseif ($key === 'v0') {
            $provided = $value;
        }
    }
    if ($timestamp === '' || $provided === '') {
        return false;
    }

    $expected = hash_hmac('sha256', $timestamp . '.' . $raw, $secret);
    return hash_equals($expected, $provided);
}

function extract_webhook_transcript(array $payload): string
{
    $candidates = [
        $payload['transcript'] ?? null,
        $payload['summary'] ?? null,
        $payload['data']['transcript'] ?? null,
        $payload['data']['summary'] ?? null,
        $payload['analysis']['transcript_summary'] ?? null,
        $payload['data']['analysis']['transcript_summary'] ?? null,
    ];
    $parts = [];
    foreach ($candidates as $candidate) {
        if (is_string($candidate) && trim($candidate) !== '') {
            $parts[] = trim($candidate);
        } elseif (is_array($candidate)) {
            $parts[] = transcript_array_to_text($candidate);
        }
    }
    foreach (['messages', 'conversation', 'data'] as $key) {
        if (!empty($payload[$key]) && is_array($payload[$key])) {
            $parts[] = transcript_array_to_text($payload[$key]);
        }
    }
    return trim(implode("\n\n", array_values(array_filter($parts))));
}

function transcript_array_to_text(array $items): string
{
    $lines = [];
    foreach ($items as $key => $item) {
        if (is_array($item)) {
            $role = (string) ($item['role'] ?? $item['speaker'] ?? $item['source'] ?? $key);
            $text = (string) ($item['message'] ?? $item['text'] ?? $item['content'] ?? '');
            if ($text !== '') {
                $lines[] = $role . ': ' . $text;
            } else {
                $nested = transcript_array_to_text($item);
                if ($nested !== '') {
                    $lines[] = $nested;
                }
            }
        } elseif (is_string($item) && trim($item) !== '') {
            $lines[] = trim($item);
        }
    }
    return trim(implode("\n", $lines));
}

