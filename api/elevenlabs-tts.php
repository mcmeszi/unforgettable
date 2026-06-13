<?php
require dirname(__DIR__) . '/app/bootstrap.php';
require dirname(__DIR__) . '/app/elevenlabs.php';
require_login();

$data = request_json();
$text = trim((string) ($data['text'] ?? ''));
if ($text === '') {
    json_response(['ok' => false, 'error' => 'Nincs felolvasható szöveg.'], 422);
}

try {
    $overrides = [];
    if (!empty($data['voice_id'])) {
        $overrides['elevenlabs_voice_id'] = (string) $data['voice_id'];
    }
    if (!empty($data['model_id'])) {
        $overrides['elevenlabs_tts_model_id'] = (string) $data['model_id'];
    }
    $audio = elevenlabs_text_to_speech($text, $overrides);
    json_response(['ok' => true, 'audio' => $audio]);
} catch (Throwable $error) {
    json_response(['ok' => false, 'error' => $error->getMessage()], 502);
}
