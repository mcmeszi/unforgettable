<?php

declare(strict_types=1);

require dirname(__DIR__) . '/app/bootstrap.php';
require dirname(__DIR__) . '/app/integrations.php';

set_time_limit(0);

$clientId = google_secret_value('google_docs_client_id');
$clientSecret = google_secret_value('google_docs_client_secret');
$redirectUri = 'http://127.0.0.1:8765/oauth2callback';

if ($clientId === '' || $clientSecret === '') {
    fwrite(STDERR, "MISSING_CLIENT=Add google_docs_client_id and google_docs_client_secret to config/local.secrets.php first.\n");
    exit(1);
}

$state = bin2hex(random_bytes(16));
$params = [
    'client_id' => $clientId,
    'redirect_uri' => $redirectUri,
    'response_type' => 'code',
    'scope' => implode(' ', [
        'https://www.googleapis.com/auth/drive.file',
        'https://www.googleapis.com/auth/documents',
    ]),
    'access_type' => 'offline',
    'prompt' => 'consent',
    'state' => $state,
];
$authUrl = 'https://accounts.google.com/o/oauth2/v2/auth?' . http_build_query($params);

echo "Open this URL in your browser:\n{$authUrl}\n\n";
echo "Waiting for Google OAuth callback on {$redirectUri} ...\n";
flush();

$server = @stream_socket_server('tcp://127.0.0.1:8765', $errno, $errstr);
if (!$server) {
    fwrite(STDERR, "CALLBACK_SERVER_ERROR={$errstr}\n");
    exit(1);
}
stream_set_timeout($server, 900);
$conn = @stream_socket_accept($server, 900);
if (!$conn) {
    fclose($server);
    fwrite(STDERR, "CALLBACK_TIMEOUT=No OAuth callback received within 15 minutes.\n");
    exit(1);
}

$request = '';
while (!str_contains($request, "\r\n\r\n") && !feof($conn)) {
    $request .= (string) fread($conn, 1024);
}

$firstLine = strtok($request, "\r\n") ?: '';
if (!preg_match('#GET\s+([^ ]+)#', $firstLine, $matches)) {
    google_oauth_http_response($conn, 'Invalid OAuth callback request.');
    fclose($conn);
    fclose($server);
    exit(1);
}

$callbackUrl = 'http://127.0.0.1:8765' . $matches[1];
$query = [];
parse_str((string) parse_url($callbackUrl, PHP_URL_QUERY), $query);

if (($query['state'] ?? '') !== $state) {
    google_oauth_http_response($conn, 'OAuth state mismatch. You can close this tab.');
    fclose($conn);
    fclose($server);
    fwrite(STDERR, "STATE_MISMATCH=yes\n");
    exit(1);
}

$code = (string) ($query['code'] ?? '');
if ($code === '') {
    google_oauth_http_response($conn, 'No OAuth code received. You can close this tab.');
    fclose($conn);
    fclose($server);
    fwrite(STDERR, "MISSING_CODE=yes\n");
    exit(1);
}

$token = google_token_request(http_build_query([
    'client_id' => $clientId,
    'client_secret' => $clientSecret,
    'code' => $code,
    'grant_type' => 'authorization_code',
    'redirect_uri' => $redirectUri,
]));

if (empty($token['refresh_token'])) {
    google_oauth_http_response($conn, 'Google returned no refresh token. You can close this tab.');
    fclose($conn);
    fclose($server);
    fwrite(STDERR, "NO_REFRESH_TOKEN=yes\n");
    fwrite(STDERR, "TOKEN_STATUS=" . app_redact_secrets(json_encode($token, JSON_UNESCAPED_UNICODE)) . "\n");
    exit(1);
}

update_local_secret('google_docs_refresh_token', (string) $token['refresh_token']);
update_local_secret('google_docs_service_account_json_path', '');

google_oauth_http_response($conn, 'Unforgettable Google Docs connection is ready. You can close this tab.');
fclose($conn);
fclose($server);

echo "GOOGLE_OAUTH_CONNECTED=yes\n";
echo "REFRESH_TOKEN_STORED=yes\n";

function google_secret_value(string $key): string
{
    global $secrets;
    return trim((string) ($secrets[$key] ?? ''));
}

function google_oauth_http_response($conn, string $message): void
{
    $html = '<!doctype html><meta charset="utf-8"><title>Unforgettable Google OAuth</title>'
        . '<body style="font:16px system-ui;margin:48px;line-height:1.5"><h1>Unforgettable</h1><p>'
        . htmlspecialchars($message, ENT_QUOTES, 'UTF-8')
        . '</p></body>';
    fwrite($conn, "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: " . strlen($html) . "\r\n\r\n" . $html);
}

function update_local_secret(string $key, string $value): void
{
    $file = app_path('config/local.secrets.php');
    $content = (string) file_get_contents($file);
    $encoded = var_export($value, true);
    $line = "    '{$key}' => {$encoded},";

    if (preg_match('/^[ \t]*\'' . preg_quote($key, '/') . '\'\s*=>\s*.*,$/m', $content)) {
        $content = preg_replace('/^[ \t]*\'' . preg_quote($key, '/') . '\'\s*=>\s*.*,$/m', $line, $content) ?? $content;
    } else {
        $content = preg_replace('/\n\];\s*$/', "\n{$line}\n];\n", $content) ?? $content;
    }

    file_put_contents($file, $content, LOCK_EX);
}
