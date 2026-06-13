<?php

declare(strict_types=1);

function session_share_content(array $session): string
{
    $latest = latest_output($session);
    $edited = (string) ($session['user_edited_output']['content'] ?? '');
    $raw = implode("\n\n", array_map(fn ($part) => (string) ($part['raw_transcript'] ?? ''), $session['parts'] ?? []));
    $final = $edited !== '' ? $edited : (string) ($latest['markdown'] ?? '');

    return "# Unforgettable session\n\n"
        . "Session: " . (string) ($session['title'] ?? $session['id']) . "\n"
        . "Dátum: " . date('Y-m-d H:i', strtotime((string) ($session['created_at'] ?? 'now'))) . "\n"
        . "Session ID: " . (string) ($session['id'] ?? '') . "\n\n"
        . "## Rövid összefoglaló\n\n" . (string) ($latest['summary'] ?? 'Nincs összefoglaló.') . "\n\n"
        . "## Final output\n\n" . ($final !== '' ? $final : 'Nincs final output.') . "\n\n"
        . "## Nyers transcript\n\n" . ($raw !== '' ? $raw : 'Nincs transcript.') . "\n";
}

function append_action_log(string $sessionId, string $type, array $payload): void
{
    ensure_storage();
    $logFile = data_path('actions/' . safe_id($sessionId) . '.jsonl');
    $entry = array_merge([
        'type' => $type,
        'created_at' => now_iso(),
    ], $payload);
    file_put_contents($logFile, json_encode($entry, JSON_UNESCAPED_UNICODE) . PHP_EOL, FILE_APPEND | LOCK_EX);
}

function openai_extract_text(array $response): string
{
    if (isset($response['output_text']) && is_string($response['output_text'])) {
        return trim($response['output_text']);
    }
    $chunks = [];
    foreach (($response['output'] ?? []) as $item) {
        foreach (($item['content'] ?? []) as $content) {
            if (isset($content['text']) && is_string($content['text'])) {
                $chunks[] = $content['text'];
            }
        }
    }
    return trim(implode("\n", $chunks));
}

function create_openai_session_summary(array $session): array
{
    $settings = app_settings();
    if (openai_api_key() === '') {
        return [
            'status' => 'not_configured',
            'message' => 'OpenAI API kulcs nincs beállítva.',
        ];
    }
    if (!function_exists('curl_init')) {
        throw new RuntimeException('A PHP cURL extension szükséges az OpenAI integrációhoz.');
    }

    $payload = [
        'model' => openai_summary_model(),
        'instructions' => 'Készíts tömör, jól strukturált magyar összefoglalót. Különítsd el a tényeket, teendőket, kreatív ötleteket és kérdéseket. Ne találj ki új információt.',
        'input' => session_share_content($session),
    ];

    $curl = curl_init('https://api.openai.com/v1/responses');
    curl_setopt_array($curl, [
        CURLOPT_POST => true,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 120,
        CURLOPT_HTTPHEADER => [
            'Content-Type: application/json',
            'Authorization: Bearer ' . openai_api_key(),
        ],
        CURLOPT_POSTFIELDS => json_encode($payload, JSON_UNESCAPED_UNICODE),
    ] + app_curl_ca_options());
    $body = curl_exec($curl);
    $status = (int) curl_getinfo($curl, CURLINFO_RESPONSE_CODE);
    $error = curl_error($curl);
    curl_close($curl);

    if ($body === false || $error !== '') {
        throw new RuntimeException('OpenAI hálózati hiba: ' . $error);
    }
    $decoded = json_decode((string) $body, true);
    if ($status < 200 || $status >= 300) {
        $message = is_array($decoded) ? json_encode($decoded, JSON_UNESCAPED_UNICODE) : (string) $body;
        throw new RuntimeException('OpenAI API hiba (' . $status . '): ' . app_redact_secrets($message));
    }

    $summary = is_array($decoded) ? openai_extract_text($decoded) : '';
    if ($summary === '') {
        $summary = 'Az OpenAI választ adott, de nem sikerült szöveges összefoglalót kinyerni.';
    }

    $file = data_path('actions/' . safe_id((string) $session['id']) . '_openai_summary.md');
    file_put_contents($file, $summary, LOCK_EX);

    return [
        'status' => 'sent',
        'model' => $payload['model'],
        'summary' => $summary,
        'file' => $file,
    ];
}

function dispatch_session_email(array $session, string $to = ''): array
{
    $settings = app_settings();
    $recipient = filter_var($to ?: (string) ($settings['email_default_to'] ?? ''), FILTER_VALIDATE_EMAIL);
    if (!$recipient) {
        return [
            'status' => 'not_configured',
            'message' => 'Nincs érvényes címzett email cím beállítva.',
        ];
    }

    $subject = 'Unforgettable session - ' . (string) ($session['title'] ?? $session['id']);
    $content = session_share_content($session);
    $file = data_path('actions/' . safe_id((string) $session['id']) . '_email.md');
    file_put_contents($file, $content, LOCK_EX);

    if (empty($settings['email_enabled'])) {
        return [
            'status' => 'prepared',
            'message' => 'Email küldés nincs bekapcsolva, a tartalom előkészítve.',
            'to' => $recipient,
            'file' => $file,
        ];
    }

    $from = filter_var((string) ($settings['email_from'] ?? ''), FILTER_VALIDATE_EMAIL) ?: 'unforgettable@localhost';
    $headers = [
        'From: ' . $from,
        'Content-Type: text/plain; charset=UTF-8',
    ];
    $sent = function_exists('mail') && mail($recipient, $subject, $content, implode("\r\n", $headers));

    return [
        'status' => $sent ? 'sent' : 'failed',
        'to' => $recipient,
        'from' => $from,
        'file' => $file,
        'message' => $sent ? 'Email elküldve.' : 'A PHP mail() nem tudta elküldeni az emailt ezen a szerveren.',
    ];
}

function prepare_google_doc_export(array $session): array
{
    $settings = app_settings();
    $content = session_share_content($session);
    $file = data_path('actions/' . safe_id((string) $session['id']) . '_google_doc.md');
    file_put_contents($file, $content, LOCK_EX);

    if (!empty($settings['google_integration_paused'])) {
        return [
            'status' => 'paused',
            'message' => (string) ($settings['google_paused_reason'] ?? 'Google Docs/Drive integráció pihentetve.'),
            'folder_id' => (string) ($settings['google_docs_folder_id'] ?? ''),
            'file' => $file,
        ];
    }

    if (!empty($settings['google_docs_enabled'])) {
        $auth = google_docs_token();
        if ($auth['status'] === 'ready') {
            $doc = google_drive_upload_text_document(
                google_session_filename($session, 'doc'),
                $content,
                'text/markdown; charset=UTF-8',
                (string) ($settings['google_docs_folder_id'] ?? ''),
                (string) $auth['access_token']
            );
            return [
                'status' => 'created',
                'message' => 'Google Docs dokumentum létrehozva.',
                'folder_id' => (string) ($settings['google_docs_folder_id'] ?? ''),
                'file' => $file,
                'google_doc' => $doc,
            ];
        }

        return [
            'status' => 'needs_google_auth',
            'message' => $auth['message'],
            'folder_id' => (string) ($settings['google_docs_folder_id'] ?? ''),
            'file' => $file,
        ];
    }

    return [
        'status' => 'prepared',
        'message' => 'Google Docs közvetlen létrehozás nincs bekapcsolva, a dokumentumtartalom előkészítve.',
        'folder_id' => (string) ($settings['google_docs_folder_id'] ?? ''),
        'file' => $file,
    ];
}

function google_session_filename(array $session, string $suffix): string
{
    $created = strtotime((string) ($session['created_at'] ?? 'now')) ?: time();
    $title = trim((string) ($session['title'] ?? $session['id'] ?? 'session'));
    $slug = trim((string) preg_replace('/[^a-zA-Z0-9_-]+/', '-', app_ascii_slug($title)), '-');
    return date('Y-m-d_H-i_', $created) . ($slug !== '' ? $slug : 'session') . '_' . $suffix;
}

function google_docs_token(): array
{
    global $secrets;

    $direct = trim((string) ($secrets['google_docs_access_token'] ?? ''));
    if ($direct !== '') {
        return ['status' => 'ready', 'access_token' => $direct, 'source' => 'access_token'];
    }

    $refresh = trim((string) ($secrets['google_docs_refresh_token'] ?? ''));
    $clientId = trim((string) ($secrets['google_docs_client_id'] ?? ''));
    $clientSecret = trim((string) ($secrets['google_docs_client_secret'] ?? ''));
    if ($refresh !== '' && $clientId !== '' && $clientSecret !== '') {
        return google_oauth_refresh_token($refresh, $clientId, $clientSecret);
    }

    $serviceAccount = google_service_account_credentials();
    if ($serviceAccount) {
        return google_service_account_access_token($serviceAccount);
    }

    return [
        'status' => 'not_configured',
        'message' => 'Google Docs OAuth/service account nincs beállítva. Folder ID önmagában nem elég a natív Google Doc létrehozáshoz.',
    ];
}

function google_service_account_credentials(): ?array
{
    global $secrets;

    $raw = trim((string) ($secrets['google_docs_service_account_json'] ?? ''));
    if ($raw === '') {
        $path = trim((string) ($secrets['google_docs_service_account_json_path'] ?? ''));
        if ($path !== '' && is_file($path)) {
            $raw = (string) file_get_contents($path);
        }
    }
    if ($raw === '') {
        return null;
    }

    $decoded = json_decode($raw, true);
    return is_array($decoded) ? $decoded : null;
}

function google_oauth_refresh_token(string $refreshToken, string $clientId, string $clientSecret): array
{
    $body = http_build_query([
        'client_id' => $clientId,
        'client_secret' => $clientSecret,
        'refresh_token' => $refreshToken,
        'grant_type' => 'refresh_token',
    ]);
    $response = google_token_request($body);
    if (!empty($response['access_token'])) {
        return ['status' => 'ready', 'access_token' => (string) $response['access_token'], 'source' => 'refresh_token'];
    }
    return ['status' => 'error', 'message' => 'Google OAuth refresh tokenből nem jött access token.'];
}

function google_service_account_access_token(array $credentials): array
{
    if (!function_exists('openssl_sign')) {
        return ['status' => 'error', 'message' => 'Az openssl PHP extension szükséges a Google service account JWT aláíráshoz.'];
    }
    $clientEmail = (string) ($credentials['client_email'] ?? '');
    $privateKey = (string) ($credentials['private_key'] ?? '');
    $tokenUri = (string) ($credentials['token_uri'] ?? 'https://oauth2.googleapis.com/token');
    if ($clientEmail === '' || $privateKey === '') {
        return ['status' => 'error', 'message' => 'Hiányos Google service account JSON.'];
    }

    $now = time();
    $jwtHeader = google_base64_url(json_encode(['alg' => 'RS256', 'typ' => 'JWT'], JSON_UNESCAPED_SLASHES));
    $jwtClaims = google_base64_url(json_encode([
        'iss' => $clientEmail,
        'scope' => 'https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/documents',
        'aud' => $tokenUri,
        'iat' => $now,
        'exp' => $now + 3600,
    ], JSON_UNESCAPED_SLASHES));
    $unsigned = $jwtHeader . '.' . $jwtClaims;
    $signature = '';
    if (!openssl_sign($unsigned, $signature, $privateKey, OPENSSL_ALGO_SHA256)) {
        return ['status' => 'error', 'message' => 'Nem sikerült aláírni a Google service account JWT-t.'];
    }

    $response = google_token_request(http_build_query([
        'grant_type' => 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        'assertion' => $unsigned . '.' . google_base64_url($signature),
    ]), $tokenUri);
    if (!empty($response['access_token'])) {
        return ['status' => 'ready', 'access_token' => (string) $response['access_token'], 'source' => 'service_account'];
    }
    return ['status' => 'error', 'message' => 'Google service account token kérésből nem jött access token.'];
}

function google_base64_url(string $value): string
{
    return rtrim(strtr(base64_encode($value), '+/', '-_'), '=');
}

function google_token_request(string $body, string $url = 'https://oauth2.googleapis.com/token'): array
{
    if (!function_exists('curl_init')) {
        return ['status' => 'error', 'message' => 'A PHP cURL extension szükséges a Google integrációhoz.'];
    }
    $curl = curl_init($url);
    curl_setopt_array($curl, [
        CURLOPT_POST => true,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 60,
        CURLOPT_HTTPHEADER => ['Content-Type: application/x-www-form-urlencoded'],
        CURLOPT_POSTFIELDS => $body,
    ] + app_curl_ca_options());
    $raw = curl_exec($curl);
    $status = (int) curl_getinfo($curl, CURLINFO_RESPONSE_CODE);
    $error = curl_error($curl);
    curl_close($curl);
    if ($raw === false || $error !== '') {
        return ['status' => 'error', 'message' => 'Google token hálózati hiba: ' . $error];
    }
    $decoded = json_decode((string) $raw, true);
    if ($status < 200 || $status >= 300) {
        return ['status' => 'error', 'message' => 'Google token API hiba (' . $status . '): ' . app_redact_secrets((string) $raw)];
    }
    return is_array($decoded) ? $decoded : [];
}

function google_drive_upload_text_document(string $name, string $content, string $contentType, string $folderId, string $accessToken): array
{
    if (!function_exists('curl_init')) {
        throw new RuntimeException('A PHP cURL extension szükséges a Google Drive integrációhoz.');
    }

    $boundary = 'unforgettable_' . bin2hex(random_bytes(8));
    $metadata = [
        'name' => $name,
        'mimeType' => 'application/vnd.google-apps.document',
    ];
    if ($folderId !== '') {
        $metadata['parents'] = [$folderId];
    }
    $body = "--{$boundary}\r\n"
        . "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        . json_encode($metadata, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES)
        . "\r\n--{$boundary}\r\n"
        . "Content-Type: {$contentType}\r\n\r\n"
        . $content
        . "\r\n--{$boundary}--";

    $curl = curl_init('https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true&fields=id,name,webViewLink,mimeType');
    curl_setopt_array($curl, [
        CURLOPT_POST => true,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 120,
        CURLOPT_HTTPHEADER => [
            'Authorization: Bearer ' . $accessToken,
            'Content-Type: multipart/related; boundary=' . $boundary,
        ],
        CURLOPT_POSTFIELDS => $body,
    ] + app_curl_ca_options());
    $raw = curl_exec($curl);
    $status = (int) curl_getinfo($curl, CURLINFO_RESPONSE_CODE);
    $error = curl_error($curl);
    curl_close($curl);

    if ($raw === false || $error !== '') {
        throw new RuntimeException('Google Drive hálózati hiba: ' . $error);
    }
    $decoded = json_decode((string) $raw, true);
    if ($status < 200 || $status >= 300) {
        throw new RuntimeException('Google Drive API hiba (' . $status . '): ' . app_redact_secrets((string) $raw));
    }
    return is_array($decoded) ? $decoded : ['raw' => (string) $raw];
}

function upload_session_exports_to_drive(array $session): array
{
    $settings = app_settings();
    if (!empty($settings['google_integration_paused'])) {
        return [
            'status' => 'paused',
            'message' => (string) ($settings['google_paused_reason'] ?? 'Google Docs/Drive integráció pihentetve.'),
        ];
    }

    if (empty($settings['drive_enabled'])) {
        return [
            'status' => 'stub',
            'message' => 'Drive export nincs bekapcsolva.',
        ];
    }

    $auth = google_docs_token();
    if ($auth['status'] !== 'ready') {
        return [
            'status' => 'needs_google_auth',
            'message' => $auth['message'],
            'folder_hint' => 'Creative Archive/' . date('Y/m', strtotime((string) ($session['created_at'] ?? 'now'))),
        ];
    }

    $latest = latest_output($session);
    if (!$latest) {
        return ['status' => 'no_output', 'message' => 'Nincs feltölthető output.'];
    }

    $raw = implode("\n\n", array_map(fn ($part) => (string) ($part['raw_transcript'] ?? ''), $session['parts'] ?? []));
    $base = google_session_filename($session, 'export');
    $folderId = (string) ($settings['google_docs_folder_id'] ?? '');
    $files = [
        'output' => google_drive_upload_text_document($base . '_output', (string) ($latest['markdown'] ?? ''), 'text/markdown; charset=UTF-8', $folderId, (string) $auth['access_token']),
        'transcript' => google_drive_upload_text_document($base . '_transcript', $raw, 'text/plain; charset=UTF-8', $folderId, (string) $auth['access_token']),
        'data' => google_drive_upload_text_document($base . '_data', json_encode($session, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT), 'application/json; charset=UTF-8', $folderId, (string) $auth['access_token']),
    ];

    return [
        'status' => 'uploaded',
        'folder_id' => $folderId,
        'files' => $files,
    ];
}
