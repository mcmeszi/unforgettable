<?php
require dirname(__DIR__) . '/app/bootstrap.php';
require dirname(__DIR__) . '/app/elevenlabs.php';
require_login();

$manual = trim((string) ($_POST['transcript'] ?? ''));
if ($manual !== '') {
    json_response([
        'ok' => true,
        'provider' => 'manual',
        'message' => 'Kézi transcript mentve.',
        'raw_transcript' => $manual,
    ]);
}

if (empty($_FILES['audio']) || !is_uploaded_file($_FILES['audio']['tmp_name'])) {
    json_response([
        'ok' => false,
        'error' => 'Nincs audio fájl. Böngészős SpeechRecognition vagy kézi transcript használható fallbackként.',
    ], 422);
}

if (!elevenlabs_is_configured()) {
    json_response([
        'ok' => false,
        'error' => 'ElevenLabs API kulcs nincs beállítva, ezért az STT nem futtatható.',
    ], 422);
}

$originalName = basename((string) ($_FILES['audio']['name'] ?? 'recording.webm'));
$mime = (string) ($_FILES['audio']['type'] ?? 'audio/webm');
$tmpFile = data_path('tmp/' . make_id('audio') . '_' . preg_replace('/[^a-zA-Z0-9_.-]/', '-', $originalName));

try {
    if (!move_uploaded_file($_FILES['audio']['tmp_name'], $tmpFile)) {
        throw new RuntimeException('Nem sikerült az ideiglenes audio mentése.');
    }
    $transcription = elevenlabs_speech_to_text($tmpFile, $originalName, $mime);
    json_response([
        'ok' => true,
        'provider' => 'elevenlabs',
        'raw_transcript' => $transcription['text'],
        'language_code' => $transcription['language_code'],
        'details' => $transcription['raw'],
    ]);
} catch (Throwable $error) {
    json_response(['ok' => false, 'error' => $error->getMessage()], 502);
} finally {
    if (is_file($tmpFile)) {
        unlink($tmpFile);
    }
}
