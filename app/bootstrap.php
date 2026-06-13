<?php

declare(strict_types=1);

$config = require dirname(__DIR__) . '/config/config.php';
$secrets = require dirname(__DIR__) . '/config/secrets.php';

if (session_status() !== PHP_SESSION_ACTIVE) {
    session_name('unforgettable_session');
    session_start();
}

function app_path(string $path = ''): string
{
    return APP_ROOT . ($path ? '/' . ltrim($path, '/') : '');
}

function data_path(string $path = ''): string
{
    return DATA_ROOT . ($path ? '/' . ltrim($path, '/') : '');
}

function export_path(string $path = ''): string
{
    return EXPORT_ROOT . ($path ? '/' . ltrim($path, '/') : '');
}

function ensure_storage(): void
{
    $dirs = [
        'sessions', 'transcripts', 'outputs', 'research', 'exports',
        'digests', 'settings', 'logs', 'audio', 'tmp', 'actions',
    ];
    foreach ($dirs as $dir) {
        $path = data_path($dir);
        if (!is_dir($path)) {
            mkdir($path, 0775, true);
        }
    }
    foreach (['pdf', 'markdown', 'txt', 'json'] as $dir) {
        $path = export_path($dir);
        if (!is_dir($path)) {
            mkdir($path, 0775, true);
        }
    }
}

function app_settings(): array
{
    global $config, $secrets;
    $defaults = [
        'digest_hour' => (string) ($config['digest_hour'] ?? '08:00'),
        'speech_language' => 'hu-HU',
        'notes_shortcut_url' => (string) ($secrets['notes_shortcut_url'] ?? ''),
        'drive_enabled' => !empty($secrets['drive_enabled']),
        'email_enabled' => !empty($secrets['email_enabled']),
        'email_default_to' => (string) ($secrets['email_default_to'] ?? ''),
        'email_from' => (string) ($secrets['email_from'] ?? 'unforgettable@localhost'),
        'google_docs_enabled' => !empty($secrets['google_docs_enabled']),
        'google_docs_folder_id' => (string) ($secrets['google_docs_folder_id'] ?? ''),
        'google_integration_paused' => false,
        'google_paused_reason' => '',
        'public_base_url' => (string) ($secrets['public_base_url'] ?? ''),
        'openai_api_key' => (string) ($secrets['openai_api_key'] ?? ''),
        'openai_model' => (string) ($secrets['openai_model'] ?? 'gpt-4.1'),
        'openai_summary_model' => (string) ($secrets['openai_summary_model'] ?? 'gpt-4.1'),
        'auto_generate_digest' => false,
        'audio_provider' => 'browser',
        'elevenlabs_api_key' => (string) ($secrets['elevenlabs_api_key'] ?? ''),
        'elevenlabs_agent_tool_secret' => (string) ($secrets['elevenlabs_agent_tool_secret'] ?? ''),
        'elevenlabs_webhook_secret' => (string) ($secrets['elevenlabs_webhook_secret'] ?? ''),
        'elevenlabs_agent_id' => '',
        'elevenlabs_voice_id' => 'pNInz6obpgDQGcFmaJgB',
        'elevenlabs_voice_name' => 'Adam',
        'elevenlabs_tts_model_id' => 'eleven_multilingual_v2',
        'elevenlabs_stt_model_id' => 'scribe_v2',
        'elevenlabs_language_code' => 'hu',
        'elevenlabs_output_format' => 'mp3_44100_128',
        'elevenlabs_stability' => 0.5,
        'elevenlabs_similarity_boost' => 0.75,
        'elevenlabs_diarize' => false,
    ];
    $file = data_path('settings/app.json');
    if (!is_file($file)) {
        return $defaults;
    }
    $stored = json_decode((string) file_get_contents($file), true);
    return is_array($stored) ? array_merge($defaults, $stored) : $defaults;
}

function save_app_settings(array $settings): array
{
    $current = app_settings();
    $next = array_merge($current, [
        'digest_hour' => preg_match('/^\d{2}:\d{2}$/', (string) ($settings['digest_hour'] ?? ''))
            ? (string) $settings['digest_hour']
            : $current['digest_hour'],
        'speech_language' => trim((string) ($settings['speech_language'] ?? $current['speech_language'])) ?: $current['speech_language'],
        'notes_shortcut_url' => trim((string) ($settings['notes_shortcut_url'] ?? $current['notes_shortcut_url'])),
        'drive_enabled' => !empty($settings['drive_enabled']),
        'email_enabled' => !empty($settings['email_enabled']),
        'email_default_to' => filter_var((string) ($settings['email_default_to'] ?? ''), FILTER_VALIDATE_EMAIL) ? (string) $settings['email_default_to'] : $current['email_default_to'],
        'email_from' => filter_var((string) ($settings['email_from'] ?? ''), FILTER_VALIDATE_EMAIL) ? (string) $settings['email_from'] : $current['email_from'],
        'google_docs_enabled' => !empty($settings['google_docs_enabled']),
        'google_docs_folder_id' => trim((string) ($settings['google_docs_folder_id'] ?? $current['google_docs_folder_id'])),
        'google_integration_paused' => array_key_exists('google_integration_paused', $settings)
            ? !empty($settings['google_integration_paused'])
            : !empty($current['google_integration_paused']),
        'google_paused_reason' => trim((string) ($settings['google_paused_reason'] ?? $current['google_paused_reason'])),
        'public_base_url' => rtrim(trim((string) ($settings['public_base_url'] ?? $current['public_base_url'])), '/'),
        'openai_api_key' => trim((string) ($settings['openai_api_key'] ?? '')) !== '' ? trim((string) $settings['openai_api_key']) : $current['openai_api_key'],
        'openai_model' => trim((string) ($settings['openai_model'] ?? $current['openai_model'])) ?: $current['openai_model'],
        'openai_summary_model' => trim((string) ($settings['openai_summary_model'] ?? $current['openai_summary_model'])) ?: $current['openai_summary_model'],
        'auto_generate_digest' => !empty($settings['auto_generate_digest']),
        'audio_provider' => in_array(($settings['audio_provider'] ?? ''), ['browser', 'elevenlabs'], true) ? (string) $settings['audio_provider'] : $current['audio_provider'],
        'elevenlabs_api_key' => trim((string) ($settings['elevenlabs_api_key'] ?? '')) !== '' ? trim((string) $settings['elevenlabs_api_key']) : $current['elevenlabs_api_key'],
        'elevenlabs_agent_id' => trim((string) ($settings['elevenlabs_agent_id'] ?? $current['elevenlabs_agent_id'])),
        'elevenlabs_voice_id' => trim((string) ($settings['elevenlabs_voice_id'] ?? $current['elevenlabs_voice_id'])),
        'elevenlabs_voice_name' => trim((string) ($settings['elevenlabs_voice_name'] ?? $current['elevenlabs_voice_name'])) ?: $current['elevenlabs_voice_name'],
        'elevenlabs_tts_model_id' => trim((string) ($settings['elevenlabs_tts_model_id'] ?? $current['elevenlabs_tts_model_id'])) ?: $current['elevenlabs_tts_model_id'],
        'elevenlabs_stt_model_id' => trim((string) ($settings['elevenlabs_stt_model_id'] ?? $current['elevenlabs_stt_model_id'])) ?: $current['elevenlabs_stt_model_id'],
        'elevenlabs_language_code' => trim((string) ($settings['elevenlabs_language_code'] ?? $current['elevenlabs_language_code'])) ?: $current['elevenlabs_language_code'],
        'elevenlabs_output_format' => trim((string) ($settings['elevenlabs_output_format'] ?? $current['elevenlabs_output_format'])) ?: $current['elevenlabs_output_format'],
        'elevenlabs_stability' => max(0, min(1, (float) ($settings['elevenlabs_stability'] ?? $current['elevenlabs_stability']))),
        'elevenlabs_similarity_boost' => max(0, min(1, (float) ($settings['elevenlabs_similarity_boost'] ?? $current['elevenlabs_similarity_boost']))),
        'elevenlabs_diarize' => !empty($settings['elevenlabs_diarize']),
    ]);
    ensure_storage();
    file_put_contents(data_path('settings/app.json'), json_encode($next, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT), LOCK_EX);
    return $next;
}

function save_app_settings_patch(array $patch): array
{
    ensure_storage();
    $file = data_path('settings/app.json');
    $stored = [];
    if (is_file($file)) {
        $decoded = json_decode((string) file_get_contents($file), true);
        $stored = is_array($decoded) ? $decoded : [];
    }
    $clean = array_filter($patch, fn ($value) => $value !== null);
    file_put_contents($file, json_encode(array_merge($stored, $clean), JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT), LOCK_EX);
    return app_settings();
}

function public_app_settings(array $settings): array
{
    unset($settings['elevenlabs_api_key']);
    unset($settings['elevenlabs_agent_tool_secret']);
    unset($settings['elevenlabs_webhook_secret']);
    unset($settings['openai_api_key']);
    $settings['elevenlabs_configured'] = elevenlabs_api_key() !== '';
    $settings['openai_configured'] = openai_api_key() !== '';
    $settings['google_docs_auth_configured'] = google_docs_auth_configured();
    return $settings;
}

function elevenlabs_api_key(): string
{
    $settings = app_settings();
    return trim((string) ($settings['elevenlabs_api_key'] ?? ''));
}

function openai_api_key(): string
{
    $settings = app_settings();
    return trim((string) ($settings['openai_api_key'] ?? ''));
}

function openai_summary_model(): string
{
    $settings = app_settings();
    return trim((string) ($settings['openai_summary_model'] ?? '')) ?: 'gpt-4.1';
}

function elevenlabs_agent_tool_secret(): string
{
    $settings = app_settings();
    return trim((string) ($settings['elevenlabs_agent_tool_secret'] ?? ''));
}

function elevenlabs_webhook_secret(): string
{
    $settings = app_settings();
    return trim((string) ($settings['elevenlabs_webhook_secret'] ?? ''));
}

function app_curl_ca_options(): array
{
    $candidates = [
        getenv('OPENAI_CA_BUNDLE') ?: '',
        getenv('ELEVENLABS_CA_BUNDLE') ?: '',
        getenv('CURL_CA_BUNDLE') ?: '',
        getenv('SSL_CERT_FILE') ?: '',
        app_path('config/cacert.pem'),
        'C:/Program Files/Git/mingw64/etc/ssl/certs/ca-bundle.crt',
        'C:/Program Files/Git/usr/ssl/certs/ca-bundle.crt',
    ];
    foreach ($candidates as $candidate) {
        if ($candidate !== '' && is_file($candidate)) {
            return [CURLOPT_CAINFO => $candidate];
        }
    }
    return [];
}

function app_redact_secrets(string $text): string
{
    $text = preg_replace('/(Incorrect API key provided:\s*)[^"}]+/i', '$1[REDACTED]', $text) ?? $text;
    $text = preg_replace('/("access_token"\s*:\s*")[^"]+(")/i', '$1[REDACTED]$2', $text) ?? $text;
    $text = preg_replace('/("refresh_token"\s*:\s*")[^"]+(")/i', '$1[REDACTED]$2', $text) ?? $text;
    $text = preg_replace('/ya29\.[A-Za-z0-9._\-]+/', '[REDACTED]', $text) ?? $text;
    $text = preg_replace('/sk[-_][A-Za-z0-9_\-]{12,}/', '[REDACTED]', $text) ?? $text;
    $text = preg_replace('/xi-[A-Za-z0-9_\-]{12,}/', '[REDACTED]', $text) ?? $text;
    $text = preg_replace('/xi_api_key_[A-Za-z0-9_\-]{12,}/i', '[REDACTED]', $text) ?? $text;
    $text = preg_replace('/[A-Za-z0-9_\-]{8,}\*{6,}[A-Za-z0-9_\-]{2,}/', '[REDACTED]', $text) ?? $text;
    return $text;
}

function is_logged_in(): bool
{
    return !empty($_SESSION['logged_in']);
}

function require_login(): void
{
    if (!is_logged_in()) {
        header('Location: /app/login.php');
        exit;
    }
}

function json_response(array $payload, int $status = 200): void
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
    exit;
}

function request_json(): array
{
    $raw = file_get_contents('php://input') ?: '';
    if ($raw === '') {
        return $_POST;
    }
    $decoded = json_decode($raw, true);
    return is_array($decoded) ? $decoded : [];
}

function request_header(string $name): string
{
    $key = 'HTTP_' . strtoupper(str_replace('-', '_', $name));
    if (isset($_SERVER[$key])) {
        return trim((string) $_SERVER[$key]);
    }
    if (strtolower($name) === 'content-type' && isset($_SERVER['CONTENT_TYPE'])) {
        return trim((string) $_SERVER['CONTENT_TYPE']);
    }
    if (strtolower($name) === 'authorization' && isset($_SERVER['REDIRECT_HTTP_AUTHORIZATION'])) {
        return trim((string) $_SERVER['REDIRECT_HTTP_AUTHORIZATION']);
    }
    return '';
}

function now_iso(): string
{
    return (new DateTimeImmutable('now'))->format(DateTimeInterface::ATOM);
}

function app_lower(string $text): string
{
    return function_exists('mb_strtolower') ? mb_strtolower($text, 'UTF-8') : strtolower($text);
}

function google_docs_auth_configured(): bool
{
    global $secrets;
    return trim((string) ($secrets['google_docs_access_token'] ?? '')) !== ''
        || (
            trim((string) ($secrets['google_docs_refresh_token'] ?? '')) !== ''
            && trim((string) ($secrets['google_docs_client_id'] ?? '')) !== ''
            && trim((string) ($secrets['google_docs_client_secret'] ?? '')) !== ''
        )
        || trim((string) ($secrets['google_docs_service_account_json'] ?? '')) !== ''
        || trim((string) ($secrets['google_docs_service_account_json_path'] ?? '')) !== '';
}

function app_setup_status(): array
{
    $settings = app_settings();
    $checks = [
        'storage' => [
            'label' => 'Lokális tárhely',
            'status' => is_dir(data_path('sessions')) && is_dir(data_path('tmp')) ? 'ok' : 'needs_attention',
            'detail' => DATA_ROOT,
        ],
        'data_protection' => [
            'label' => 'Data könyvtár védelem',
            'status' => is_file(data_path('.htaccess')) ? 'ok' : 'needs_attention',
            'detail' => is_file(data_path('.htaccess')) ? 'data/.htaccess aktív' : 'Hiányzik a data/.htaccess',
        ],
        'curl' => [
            'label' => 'PHP cURL',
            'status' => function_exists('curl_init') ? 'ok' : 'blocked',
            'detail' => function_exists('curl_init') ? 'betöltve' : 'szükséges API hívásokhoz',
        ],
        'openssl' => [
            'label' => 'PHP OpenSSL',
            'status' => extension_loaded('openssl') ? 'ok' : 'needs_attention',
            'detail' => extension_loaded('openssl') ? 'betöltve' : 'Google service account/OAuth JWT-hez szükséges',
        ],
        'elevenlabs_key' => [
            'label' => 'ElevenLabs API',
            'status' => elevenlabs_api_key() !== '' ? 'ok' : 'blocked',
            'detail' => elevenlabs_api_key() !== '' ? 'kulcs konfigurálva' : 'hiányzó kulcs',
        ],
        'elevenlabs_agent' => [
            'label' => 'ElevenLabs agent',
            'status' => !empty($settings['elevenlabs_agent_id']) ? 'ok' : 'needs_attention',
            'detail' => !empty($settings['elevenlabs_agent_id']) ? (string) $settings['elevenlabs_agent_id'] : 'futtasd: php scripts/setup-elevenlabs-agent.php',
        ],
        'agent_tools' => [
            'label' => 'ElevenLabs HTTP toolok',
            'status' => !empty($settings['public_base_url']) ? 'ok' : 'paused',
            'detail' => !empty($settings['public_base_url']) ? (string) $settings['public_base_url'] : 'publikus app URL kell hozzá',
        ],
        'openai' => [
            'label' => 'OpenAI summary',
            'status' => openai_api_key() !== '' ? 'ok' : 'needs_attention',
            'detail' => openai_api_key() !== '' ? openai_summary_model() : 'hiányzó OpenAI kulcs',
        ],
        'email' => [
            'label' => 'Email export',
            'status' => !empty($settings['email_default_to']) ? (!empty($settings['email_enabled']) ? 'ok' : 'paused') : 'needs_attention',
            'detail' => !empty($settings['email_default_to'])
                ? (!empty($settings['email_enabled']) ? 'küldés bekapcsolva' : 'csak előkészítő mód')
                : 'nincs alapértelmezett címzett',
        ],
        'notes' => [
            'label' => 'iOS Notes Shortcut',
            'status' => !empty($settings['notes_shortcut_url']) ? 'ok' : 'needs_attention',
            'detail' => !empty($settings['notes_shortcut_url']) ? 'shortcut URL beállítva' : 'hiányzó shortcut URL',
        ],
        'digest' => [
            'label' => 'Reggeli digest',
            'status' => !empty($settings['auto_generate_digest']) ? 'ok' : 'paused',
            'detail' => 'időpont: ' . (string) ($settings['digest_hour'] ?? '08:00'),
        ],
        'google' => [
            'label' => 'Google Docs/Drive',
            'status' => !empty($settings['google_integration_paused']) ? 'paused' : (!empty($settings['google_docs_enabled']) || !empty($settings['drive_enabled']) ? 'needs_attention' : 'paused'),
            'detail' => !empty($settings['google_integration_paused'])
                ? ((string) ($settings['google_paused_reason'] ?? 'pihentetve'))
                : 'jelenleg nem fókusz',
        ],
    ];

    $counts = ['ok' => 0, 'paused' => 0, 'needs_attention' => 0, 'blocked' => 0];
    foreach ($checks as $check) {
        $status = (string) ($check['status'] ?? 'needs_attention');
        $counts[$status] = ($counts[$status] ?? 0) + 1;
    }

    return [
        'generated_at' => now_iso(),
        'counts' => $counts,
        'checks' => $checks,
    ];
}

function build_daily_digest(string $date): array
{
    $date = preg_match('/^\d{4}-\d{2}-\d{2}$/', $date) ? $date : date('Y-m-d', strtotime('-1 day'));
    $sessions = array_values(array_filter(list_sessions(), fn ($s) => date('Y-m-d', strtotime((string) $s['created_at'])) === $date));
    $digest = "# Reggeli Digest\n\n## Dátum\n{$date}\n\n## Előző napi sessionök\n\n";
    foreach ($sessions as $session) {
        $latest = latest_output($session);
        $digest .= "### " . date('H:i', strtotime((string) $session['created_at'])) . " - " . ($session['title'] ?? '') . "\n";
        $digest .= "Summary: " . ($latest['summary'] ?? '') . "\n";
        $digest .= "Fontos: " . (!empty($session['important']) ? 'igen' : 'nem') . "\n";
        $digest .= "Fő elemek: " . implode(', ', array_filter([
            count($latest['elements']['versreszletek'] ?? []) ? count($latest['elements']['versreszletek']) . ' versrészlet' : '',
            count($session['research'] ?? []) ? count($session['research']) . ' kutatás' : '',
            count($latest['elements']['otletek'] ?? []) ? count($latest['elements']['otletek']) . ' ötlet' : '',
        ])) . "\n";
        $digest .= "Export linkek: " . implode(', ', $session['exports'] ?? []) . "\n\n";
    }
    $important = array_filter($sessions, fn ($s) => !empty($s['important']));
    $digest .= "## Fontos sessionök\n" . ($important ? implode("\n", array_map(fn ($s) => '- ' . ($s['title'] ?? $s['id']), $important)) : '- Nincs külön jelölt fontos session.') . "\n\n";
    $digest .= "## Később feldolgozandó anyagok\n";
    $digest .= implode("\n", array_map(fn ($s) => '- ' . ($s['title'] ?? $s['id']), array_filter($sessions, fn ($s) => ($s['archive_priority'] ?? '') === 'high'))) ?: '- Nincs kiemelt feldolgozási tétel.';
    $digest .= "\n";
    $file = data_path('digests/' . $date . '.md');
    file_put_contents($file, $digest, LOCK_EX);

    return [
        'date' => $date,
        'session_count' => count($sessions),
        'file' => $file,
        'digest' => $digest,
    ];
}

function app_strlen(string $text): int
{
    return function_exists('mb_strlen') ? mb_strlen($text, 'UTF-8') : strlen($text);
}

function app_substr(string $text, int $start, ?int $length = null): string
{
    if (function_exists('mb_substr')) {
        return $length === null ? mb_substr($text, $start, null, 'UTF-8') : mb_substr($text, $start, $length, 'UTF-8');
    }
    return $length === null ? substr($text, $start) : substr($text, $start, $length);
}

function session_file(string $id): string
{
    return data_path('sessions/' . safe_id($id) . '.json');
}

function safe_id(string $id): string
{
    return preg_replace('/[^a-zA-Z0-9_-]/', '', basename($id)) ?: '';
}

function read_session(string $id): ?array
{
    $file = session_file($id);
    if (!is_file($file)) {
        return null;
    }
    $data = json_decode((string) file_get_contents($file), true);
    return is_array($data) ? $data : null;
}

function write_session(array $session): void
{
    ensure_storage();
    file_put_contents(
        session_file((string) $session['id']),
        json_encode($session, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT),
        LOCK_EX
    );
}

function list_sessions(): array
{
    ensure_storage();
    $sessions = [];
    foreach (glob(data_path('sessions/*.json')) ?: [] as $file) {
        $data = json_decode((string) file_get_contents($file), true);
        if (is_array($data)) {
            $sessions[] = $data;
        }
    }
    usort($sessions, fn ($a, $b) => strcmp((string) ($b['created_at'] ?? ''), (string) ($a['created_at'] ?? '')));
    return $sessions;
}

function make_id(string $prefix = 'session'): string
{
    return $prefix . '_' . (new DateTimeImmutable())->format('Y_m_d_His') . '_' . bin2hex(random_bytes(3));
}

function new_session_array(string $title = ''): array
{
    $id = make_id();
    return [
        'id' => $id,
        'title' => $title !== '' ? $title : 'Új gondolat - ' . date('H:i'),
        'created_at' => now_iso(),
        'updated_at' => now_iso(),
        'status' => 'active',
        'archived' => false,
        'important' => false,
        'keep_full_context' => false,
        'archive_priority' => 'normal',
        'parts' => [],
        'research' => [],
        'outputs' => [],
        'exports' => [],
        'notes' => ['status' => 'none'],
        'drive' => ['status' => 'none'],
    ];
}

function title_from_summary(string $summary): string
{
    $title = trim(preg_replace('/[^\p{L}\p{N}\s-]+/u', '', $summary) ?? $summary);
    return app_strlen($title) > 56 ? app_substr($title, 0, 53) . '...' : ($title ?: 'Lezárt session');
}

function latest_output(array $session): ?array
{
    $outputs = $session['outputs'] ?? [];
    if (!$outputs) {
        return null;
    }
    $latest = end($outputs);
    return is_array($latest) ? $latest : null;
}

function append_session_part(array &$session, string $raw, string $source = 'manual'): ?array
{
    $raw = trim($raw);
    if ($raw === '') {
        return null;
    }
    $part = [
        'id' => make_id('part'),
        'part_number' => count($session['parts'] ?? []) + 1,
        'created_at' => now_iso(),
        'source' => $source,
        'raw_transcript' => $raw,
        'clean_transcript' => clean_transcript($raw),
    ];
    $session['parts'][] = $part;
    file_put_contents(data_path('transcripts/' . $session['id'] . '_' . $part['id'] . '.txt'), $raw);
    return $part;
}

function session_has_parts(array $session): bool
{
    return count($session['parts'] ?? []) > 0;
}

function transcript_for_session(array $session, string $field = 'raw_transcript'): string
{
    return trim(implode("\n\n", array_map(fn ($part) => (string) ($part[$field] ?? ''), $session['parts'] ?? [])));
}

function important_command_detected(string $text): bool
{
    return preg_match('/(ezt tuti mentsd el|ez fontos|ezt mentsd el|ezt rakjuk el|ezt ne veszítsük el|hardcore mentés|csillag)/iu', $text) === 1;
}

function mark_session_important(array &$session): void
{
    $session['important'] = true;
    $session['keep_full_context'] = true;
    $session['archive_priority'] = 'high';
}

function normalize_session_status(string $status, array $session): string
{
    $allowed = ['active', 'paused', 'closed', 'continued', 'processing', 'exported', 'archived'];
    if (!in_array($status, $allowed, true)) {
        return (string) ($session['status'] ?? 'active');
    }
    return $status;
}

function clean_transcript(string $raw): string
{
    $text = trim(preg_replace('/[ \t]+/u', ' ', $raw) ?? $raw);
    $blocks = [
        'új versszak', 'hagyj ki egy sort', 'üres sor', 'következő versszak', 'itt legyen új versszak',
    ];
    $breaks = [
        'új sor', 'következő sor', 'sortörés', 'itt rakj entert', 'itt legyen enter',
        'itt legyen sortörés', 'ezt új sorba', 'ezt külön sorba', 'ezt rakd külön sorba',
    ];
    $punctuation = [
        'három pont' => '... ',
        'pont' => '. ',
        'vessző' => ', ',
        'kettőspont' => ': ',
        'pontosvessző' => '; ',
        'kérdőjel' => '? ',
        'felkiáltójel' => '! ',
        'gondolatjel' => ' - ',
    ];
    foreach ($blocks as $command) {
        $text = preg_replace('/\s*' . preg_quote($command, '/') . '\s*/iu', "\n\n", $text) ?? $text;
    }
    foreach ($breaks as $command) {
        $text = preg_replace('/\s*' . preg_quote($command, '/') . '\s*/iu', "\n", $text) ?? $text;
    }
    foreach ($punctuation as $command => $mark) {
        $text = preg_replace('/\s+' . preg_quote($command, '/') . '(?=\s|$)/iu', $mark, $text) ?? $text;
    }
    $text = preg_replace('/\s*(ezt töröld|az előző szót töröld|az előző mondatot töröld|az előző sort töröld|ezt a mondatot töröld|ezt ne írd le|ezt hagyd ki|mégse|scratch that)\s*/iu', ' ', $text) ?? $text;
    $text = preg_replace("/[ \t]+\n/u", "\n", $text) ?? $text;
    $text = preg_replace("/\n{3,}/u", "\n\n", $text) ?? $text;
    return trim($text);
}

function detect_elements(string $text): array
{
    $lower = app_lower($text);
    $lines = preg_split('/\R/u', trim($text)) ?: [];
    $poemLines = array_values(array_filter($lines, fn ($line) => app_strlen(trim($line)) > 0 && app_strlen(trim($line)) < 90));
    preg_match_all('/(?:nézz utána|keress|best practice|top hármat|milyen példák vannak)[^.?!\n]*/iu', $text, $research);
    preg_match_all('/(?:ötlet|workshop|kampány|projekt)[^.?!\n]*/iu', $text, $ideas);
    preg_match_all('/(?:teendő|todo|később|majd)[^.?!\n]*/iu', $text, $todos);

    return [
        'versreszletek' => count($poemLines) >= 3 ? array_slice($poemLines, 0, 12) : [],
        'szoviccek' => str_contains($lower, 'szóvicc') ? ['Szóvicc említés a transcriptben.'] : [],
        'otletek' => array_values(array_unique($ideas[0] ?? [])),
        'kutatasi_kerdesek' => array_values(array_unique($research[0] ?? [])),
        'teendok' => array_values(array_unique($todos[0] ?? [])),
    ];
}

function build_output(array $session): array
{
    $raw = implode("\n\n", array_map(fn ($p) => (string) ($p['raw_transcript'] ?? ''), $session['parts'] ?? []));
    $clean = implode("\n\n", array_map(fn ($p) => (string) ($p['clean_transcript'] ?? ''), $session['parts'] ?? []));
    $elements = detect_elements($clean ?: $raw);
    $summary = summarize_text($clean ?: $raw);
    $research = $session['research'] ?? [];

    $markdown = "# Session Output\n\n";
    $markdown .= "## Alapadatok\n";
    $markdown .= "Dátum: " . date('Y-m-d', strtotime((string) $session['created_at'])) . "\n";
    $markdown .= "Idő: " . date('H:i', strtotime((string) $session['created_at'])) . "\n";
    $markdown .= "Session ID: {$session['id']}\n";
    $markdown .= "Fontos session: " . (!empty($session['important']) ? 'igen' : 'nem') . "\n";
    $markdown .= "Státusz: {$session['status']}\n\n";
    $markdown .= "Részek száma: " . count($session['parts'] ?? []) . "\n";
    $markdown .= "Output verzió: v" . (count($session['outputs'] ?? []) + 1) . "\n\n";
    $markdown .= "## Rövid összefoglaló\n\n{$summary}\n\n";
    $markdown .= "## Nyers transcript\n\n{$raw}\n\n";
    $markdown .= "## Tisztított transcript\n\n{$clean}\n\n";
    $markdown .= "## Strukturált jegyzet\n\n" . structured_notes($elements) . "\n";
    $markdown .= "## Kutatások\n\n" . research_markdown($research) . "\n";
    $markdown .= "## Final output\n\n" . final_output($clean ?: $raw, $elements) . "\n\n";
    $markdown .= "## ChatGPT folytató prompt\n\n" . chatgpt_prompt($summary, $raw, structured_notes($elements), final_output($clean ?: $raw, $elements), $research) . "\n";

    return [
        'version' => count($session['outputs'] ?? []) + 1,
        'created_at' => now_iso(),
        'summary' => $summary,
        'elements' => $elements,
        'markdown' => $markdown,
        'chatgpt_prompt' => chatgpt_prompt($summary, $raw, structured_notes($elements), final_output($clean ?: $raw, $elements), $research),
    ];
}

function summarize_text(string $text): string
{
    $sentences = preg_split('/(?<=[.!?])\s+/u', trim($text)) ?: [];
    $first = trim($sentences[0] ?? '');
    if ($first === '') {
        return 'Nincs még elég transcript az összefoglalóhoz.';
    }
    return app_strlen($first) > 220 ? app_substr($first, 0, 217) . '...' : $first;
}

function structured_notes(array $elements): string
{
    $sections = [
        'Versrészletek' => $elements['versreszletek'] ?? [],
        'Szóviccek' => $elements['szoviccek'] ?? [],
        'Ötletek' => $elements['otletek'] ?? [],
        'Kutatási kérdések' => $elements['kutatasi_kerdesek'] ?? [],
        'Későbbi teendők' => $elements['teendok'] ?? [],
    ];
    $out = '';
    foreach ($sections as $title => $items) {
        $out .= "### {$title}\n";
        $out .= $items ? implode("\n", array_map(fn ($item) => '- ' . trim((string) $item), $items)) . "\n\n" : "- Nincs jelölt elem.\n\n";
    }
    return $out;
}

function final_output(string $text, array $elements): string
{
    if (trim($text) === '') {
        return 'A session lezárult, de még nincs feldolgozható transcript.';
    }
    $importantBits = array_merge($elements['versreszletek'] ?? [], $elements['otletek'] ?? []);
    if ($importantBits) {
        return implode("\n", array_map(fn ($item) => '- ' . trim((string) $item), array_slice($importantBits, 0, 8)));
    }
    return trim($text);
}

function research_markdown(array $research): string
{
    if (!$research) {
        return "- Nem volt kutatási kérés.\n\n";
    }
    $out = '';
    foreach ($research as $item) {
        $out .= "### Kérdés\n" . ($item['query'] ?? '') . "\n\n### Top 3 találat\n";
        foreach (($item['results'] ?? []) as $i => $result) {
            $out .= ($i + 1) . '. ' . ($result['title'] ?? '') . ' - ' . ($result['summary'] ?? '') . "\n";
        }
        $out .= "\n";
    }
    return $out;
}

function chatgpt_prompt(string $summary, string $raw, string $notes, string $final, array $research): string
{
    return "# Kontextus egy új ChatGPT beszélgetéshez\n\n"
        . "Az alábbi Unforgettable sessiont szeretném folytatni.\n\n"
        . "Kérlek:\n- vedd figyelembe a nyers transcriptet\n- ne írj át költői szöveget önkényesen\n- különítsd el a saját javaslataidat az eredeti anyagtól\n- segíts folytatni, szerkeszteni vagy rendszerezni\n\n"
        . "## Session summary\n{$summary}\n\n## Nyers transcript\n{$raw}\n\n## Strukturált jegyzet\n{$notes}\n\n## Final output\n{$final}\n\n## Kutatások\n" . research_markdown($research) . "\n## Feladat\n";
}

function write_exports(array $session): array
{
    $latest = latest_output($session);
    if (!$latest) {
        return [];
    }
    $safeTitle = preg_replace('/[^a-z0-9_-]+/i', '-', app_ascii_slug((string) ($session['title'] ?? $session['id'])));
    $version = 'v' . (string) ($latest['version'] ?? count($session['outputs'] ?? []));
    $base = date('Y-m-d_H-i_', strtotime((string) $session['created_at'])) . trim((string) $safeTitle, '-') . '_' . $version;
    $md = "markdown/{$base}.md";
    $txt = "txt/{$base}.txt";
    $json = "json/{$base}.json";
    $pdf = "pdf/{$base}.html";
    file_put_contents(export_path($md), (string) $latest['markdown']);
    file_put_contents(export_path($txt), implode("\n\n", array_map(fn ($p) => (string) ($p['raw_transcript'] ?? ''), $session['parts'] ?? [])));
    file_put_contents(export_path($json), json_encode($session, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT));
    file_put_contents(export_path($pdf), '<!doctype html><meta charset="utf-8"><title>' . htmlspecialchars((string) $session['title']) . '</title><pre style="font:15px/1.55 system-ui;white-space:pre-wrap;max-width:760px;margin:48px auto">' . htmlspecialchars((string) $latest['markdown']) . '</pre>');
    return [
        'markdown' => '/exports/' . $md,
        'txt' => '/exports/' . $txt,
        'json' => '/exports/' . $json,
        'pdf' => '/exports/' . $pdf,
    ];
}

function app_ascii_slug(string $text): string
{
    $map = [
        'á' => 'a', 'é' => 'e', 'í' => 'i', 'ó' => 'o', 'ö' => 'o', 'ő' => 'o', 'ú' => 'u', 'ü' => 'u', 'ű' => 'u',
        'Á' => 'A', 'É' => 'E', 'Í' => 'I', 'Ó' => 'O', 'Ö' => 'O', 'Ő' => 'O', 'Ú' => 'U', 'Ü' => 'U', 'Ű' => 'U',
    ];
    return strtr($text, $map);
}

ensure_storage();
