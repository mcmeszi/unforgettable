<?php

declare(strict_types=1);

function elevenlabs_is_configured(): bool
{
    return elevenlabs_api_key() !== '';
}

function elevenlabs_base_url(): string
{
    return 'https://api.elevenlabs.io';
}

function elevenlabs_json(string $method, string $path, ?array $payload = null): array
{
    if (!function_exists('curl_init')) {
        throw new RuntimeException('A PHP cURL extension szükséges az ElevenLabs integrációhoz.');
    }
    if (!elevenlabs_is_configured()) {
        throw new RuntimeException('ElevenLabs API kulcs nincs beállítva.');
    }

    $curl = curl_init(elevenlabs_base_url() . $path);
    $headers = [
        'Accept: application/json',
        'xi-api-key: ' . elevenlabs_api_key(),
    ];
    curl_setopt_array($curl, [
        CURLOPT_CUSTOMREQUEST => $method,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 90,
        CURLOPT_HTTPHEADER => $headers,
    ] + app_curl_ca_options());
    if ($payload !== null) {
        $headers[] = 'Content-Type: application/json';
        curl_setopt($curl, CURLOPT_HTTPHEADER, $headers);
        curl_setopt($curl, CURLOPT_POSTFIELDS, json_encode($payload, JSON_UNESCAPED_UNICODE));
    }

    $body = curl_exec($curl);
    $status = (int) curl_getinfo($curl, CURLINFO_RESPONSE_CODE);
    $error = curl_error($curl);
    curl_close($curl);

    if ($body === false || $error !== '') {
        throw new RuntimeException('ElevenLabs hálózati hiba: ' . $error);
    }
    $decoded = json_decode((string) $body, true);
    if ($status < 200 || $status >= 300) {
        $message = is_array($decoded) ? json_encode($decoded, JSON_UNESCAPED_UNICODE) : (string) $body;
        throw new RuntimeException('ElevenLabs API hiba (' . $status . '): ' . app_redact_secrets($message));
    }
    return is_array($decoded) ? $decoded : ['raw' => (string) $body];
}

function elevenlabs_binary(string $method, string $path, array $payload): string
{
    if (!function_exists('curl_init')) {
        throw new RuntimeException('A PHP cURL extension szükséges az ElevenLabs integrációhoz.');
    }
    if (!elevenlabs_is_configured()) {
        throw new RuntimeException('ElevenLabs API kulcs nincs beállítva.');
    }

    $curl = curl_init(elevenlabs_base_url() . $path);
    curl_setopt_array($curl, [
        CURLOPT_CUSTOMREQUEST => $method,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 120,
        CURLOPT_HTTPHEADER => [
            'Accept: audio/mpeg',
            'Content-Type: application/json',
            'xi-api-key: ' . elevenlabs_api_key(),
        ],
        CURLOPT_POSTFIELDS => json_encode($payload, JSON_UNESCAPED_UNICODE),
    ] + app_curl_ca_options());

    $body = curl_exec($curl);
    $status = (int) curl_getinfo($curl, CURLINFO_RESPONSE_CODE);
    $contentType = (string) curl_getinfo($curl, CURLINFO_CONTENT_TYPE);
    $error = curl_error($curl);
    curl_close($curl);

    if ($body === false || $error !== '') {
        throw new RuntimeException('ElevenLabs hálózati hiba: ' . $error);
    }
    if ($status < 200 || $status >= 300) {
        throw new RuntimeException('ElevenLabs API hiba (' . $status . '): ' . app_redact_secrets(app_substr((string) $body, 0, 500)));
    }
    if (!str_contains($contentType, 'audio') && $contentType !== '') {
        throw new RuntimeException('ElevenLabs nem audio választ adott: ' . $contentType);
    }
    return (string) $body;
}

function elevenlabs_multipart(string $path, array $fields): array
{
    if (!function_exists('curl_init')) {
        throw new RuntimeException('A PHP cURL extension szükséges az ElevenLabs integrációhoz.');
    }
    if (!elevenlabs_is_configured()) {
        throw new RuntimeException('ElevenLabs API kulcs nincs beállítva.');
    }

    $curl = curl_init(elevenlabs_base_url() . $path);
    curl_setopt_array($curl, [
        CURLOPT_POST => true,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 180,
        CURLOPT_HTTPHEADER => [
            'Accept: application/json',
            'xi-api-key: ' . elevenlabs_api_key(),
        ],
        CURLOPT_POSTFIELDS => $fields,
    ] + app_curl_ca_options());
    $body = curl_exec($curl);
    $status = (int) curl_getinfo($curl, CURLINFO_RESPONSE_CODE);
    $error = curl_error($curl);
    curl_close($curl);

    if ($body === false || $error !== '') {
        throw new RuntimeException('ElevenLabs hálózati hiba: ' . $error);
    }
    $decoded = json_decode((string) $body, true);
    if ($status < 200 || $status >= 300) {
        $message = is_array($decoded) ? json_encode($decoded, JSON_UNESCAPED_UNICODE) : (string) $body;
        throw new RuntimeException('ElevenLabs API hiba (' . $status . '): ' . app_redact_secrets($message));
    }
    return is_array($decoded) ? $decoded : ['raw' => (string) $body];
}

function elevenlabs_status(): array
{
    if (!elevenlabs_is_configured()) {
        return [
            'configured' => false,
            'mode' => 'not_configured',
            'message' => 'ElevenLabs API kulcs nincs beállítva.',
        ];
    }

    $capabilities = [];
    foreach ([
        'models' => '/v1/models',
        'voices' => '/v1/voices',
        'agents' => '/v1/convai/agents',
    ] as $name => $path) {
        try {
            elevenlabs_json('GET', $path);
            $capabilities[$name] = 'ok';
        } catch (Throwable $error) {
            $capabilities[$name] = app_redact_secrets($error->getMessage());
        }
    }

    try {
        $subscription = elevenlabs_json('GET', '/v1/user/subscription');
        return [
            'configured' => true,
            'mode' => 'direct_api',
            'capabilities' => $capabilities,
            'subscription' => $subscription,
        ];
    } catch (Throwable $error) {
        return [
            'configured' => true,
            'mode' => 'direct_api',
            'capabilities' => $capabilities,
            'subscription_status' => 'unavailable',
            'subscription_error' => app_redact_secrets($error->getMessage()),
        ];
    }
}

function elevenlabs_search_voices(string $query = ''): array
{
    $response = elevenlabs_json('GET', '/v1/voices');
    $voices = $response['voices'] ?? [];
    if ($query !== '') {
        $needle = app_lower($query);
        $voices = array_values(array_filter($voices, fn ($voice) => str_contains(app_lower((string) ($voice['name'] ?? '')), $needle)));
    }
    return array_map(fn ($voice) => [
        'voice_id' => (string) ($voice['voice_id'] ?? ''),
        'name' => (string) ($voice['name'] ?? ''),
        'category' => (string) ($voice['category'] ?? ''),
        'description' => (string) ($voice['description'] ?? ''),
        'preview_url' => (string) ($voice['preview_url'] ?? ''),
    ], $voices);
}

function elevenlabs_text_to_speech(string $text, array $overrides = []): array
{
    $settings = array_merge(app_settings(), $overrides);
    $voiceId = trim((string) ($settings['elevenlabs_voice_id'] ?? ''));
    if ($voiceId === '') {
        $voiceId = 'pNInz6obpgDQGcFmaJgB';
    }
    $outputFormat = rawurlencode((string) ($settings['elevenlabs_output_format'] ?? 'mp3_44100_128'));
    $payload = [
        'text' => $text,
        'model_id' => trim((string) ($settings['elevenlabs_tts_model_id'] ?? '')) ?: 'eleven_multilingual_v2',
        'voice_settings' => [
            'stability' => (float) ($settings['elevenlabs_stability'] ?? 0.5),
            'similarity_boost' => (float) ($settings['elevenlabs_similarity_boost'] ?? 0.75),
        ],
    ];

    $audio = elevenlabs_binary('POST', '/v1/text-to-speech/' . rawurlencode($voiceId) . '?output_format=' . $outputFormat, $payload);
    $file = make_id('tts') . '.mp3';
    file_put_contents(data_path('audio/' . $file), $audio, LOCK_EX);
    return [
        'file' => $file,
        'url' => '/api/audio-file.php?file=' . rawurlencode($file),
        'bytes' => strlen($audio),
        'voice_id' => $voiceId,
    ];
}

function elevenlabs_speech_to_text(string $filePath, string $fileName, string $mimeType, array $overrides = []): array
{
    $settings = array_merge(app_settings(), $overrides);
    $fields = [
        'model_id' => trim((string) ($settings['elevenlabs_stt_model_id'] ?? '')) ?: 'scribe_v1',
        'file' => new CURLFile($filePath, $mimeType ?: 'application/octet-stream', $fileName),
        'diarize' => !empty($settings['elevenlabs_diarize']) ? 'true' : 'false',
    ];
    $language = trim((string) ($settings['elevenlabs_language_code'] ?? ''));
    if ($language !== '') {
        $fields['language_code'] = $language;
    }

    $response = elevenlabs_multipart('/v1/speech-to-text', $fields);
    $text = (string) ($response['text'] ?? '');
    if ($text === '' && !empty($response['segments']) && is_array($response['segments'])) {
        $text = implode("\n", array_map(fn ($segment) => (string) ($segment['text'] ?? ''), $response['segments']));
    }
    return [
        'text' => trim($text),
        'raw' => $response,
        'language_code' => (string) ($response['language_code'] ?? $language),
    ];
}
