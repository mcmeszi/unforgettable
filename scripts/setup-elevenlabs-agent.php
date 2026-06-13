<?php

declare(strict_types=1);

require dirname(__DIR__) . '/app/bootstrap.php';
require dirname(__DIR__) . '/app/elevenlabs.php';

$blueprintFile = app_path('config/elevenlabs-agent-blueprint.json');
$blueprint = json_decode((string) file_get_contents($blueprintFile), true);
if (!is_array($blueprint)) {
    fwrite(STDERR, "BLUEPRINT_ERROR=invalid_json\n");
    exit(1);
}

$settings = app_settings();
$agentName = (string) ($blueprint['agent_name'] ?? 'Unforgettable Archivista');
$existing = find_elevenlabs_agent_by_name($agentName);
$agentId = $existing['agent_id'] ?? '';
$status = $agentId !== '' ? 'existing' : 'created';
$publicBaseUrl = rtrim((string) ($settings['public_base_url'] ?? ''), '/');
$toolsEnabled = $publicBaseUrl !== '' && elevenlabs_agent_tool_secret() !== '';

if ($agentId === '') {
    $agent = create_unforgettable_agent($blueprint, $publicBaseUrl, $toolsEnabled);
    $agentId = (string) ($agent['agent_id'] ?? '');
} elseif ($toolsEnabled) {
    update_unforgettable_agent($agentId, $blueprint, $publicBaseUrl, $toolsEnabled);
    $status = 'updated';
}

if ($agentId === '') {
    fwrite(STDERR, "AGENT_ERROR=missing_agent_id\n");
    exit(1);
}

save_app_settings_patch([
    'audio_provider' => 'elevenlabs',
    'elevenlabs_agent_id' => $agentId,
    'elevenlabs_agent_tools_enabled' => $toolsEnabled,
    'email_enabled' => !empty($settings['email_enabled']),
    'google_docs_enabled' => empty($settings['google_integration_paused']) && trim((string) ($settings['google_docs_folder_id'] ?? '')) !== '',
    'drive_enabled' => empty($settings['google_integration_paused']) && trim((string) ($settings['google_docs_folder_id'] ?? '')) !== '',
    'auto_generate_digest' => true,
]);

$setup = [
    'agent_id' => $agentId,
    'agent_name' => $agentName,
    'status' => $status,
    'tools_enabled' => $toolsEnabled,
    'public_base_url_configured' => $publicBaseUrl !== '',
    'updated_at' => now_iso(),
];
file_put_contents(data_path('settings/elevenlabs-agent-setup.json'), json_encode($setup, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT), LOCK_EX);

echo 'AGENT_STATUS=' . $status . PHP_EOL;
echo 'AGENT_ID=' . $agentId . PHP_EOL;
echo 'TOOLS_ENABLED=' . ($toolsEnabled ? 'yes' : 'no') . PHP_EOL;
echo 'PUBLIC_BASE_URL_CONFIGURED=' . ($publicBaseUrl !== '' ? 'yes' : 'no') . PHP_EOL;
echo 'APP_SETTINGS_UPDATED=yes' . PHP_EOL;

function find_elevenlabs_agent_by_name(string $name): array
{
    try {
        $response = elevenlabs_json('GET', '/v1/convai/agents');
    } catch (Throwable $error) {
        throw new RuntimeException('Nem sikerült listázni az ElevenLabs agenteket: ' . app_redact_secrets($error->getMessage()));
    }
    foreach (($response['agents'] ?? []) as $agent) {
        if ((string) ($agent['name'] ?? '') === $name) {
            return is_array($agent) ? $agent : [];
        }
    }
    return [];
}

function create_unforgettable_agent(array $blueprint, string $publicBaseUrl, bool $toolsEnabled): array
{
    return create_agent_with_llm_fallbacks(build_unforgettable_agent_payload($blueprint, $publicBaseUrl, $toolsEnabled));
}

function update_unforgettable_agent(string $agentId, array $blueprint, string $publicBaseUrl, bool $toolsEnabled): array
{
    $payload = build_unforgettable_agent_payload($blueprint, $publicBaseUrl, $toolsEnabled);
    return elevenlabs_json('PATCH', '/v1/convai/agents/' . rawurlencode($agentId), [
        'conversation_config' => $payload['conversation_config'],
        'platform_settings' => $payload['platform_settings'],
    ]);
}

function build_unforgettable_agent_payload(array $blueprint, string $publicBaseUrl, bool $toolsEnabled): array
{
    $settings = app_settings();
    $personality = is_array($blueprint['personality'] ?? null) ? $blueprint['personality'] : [];
    $systemPrompt = trim((string) ($personality['system_prompt'] ?? ''));
    $systemPrompt .= "\n\nTool-használat: archívumkeresést, mentést, emailt, Google Docs exportot és OpenAI továbbküldést csak explicit felhasználói kérésre indíts. Ha nincs elég adat a toolhoz, kérdezz vissza röviden. Csend közben ne beszélj.";
    if (!$toolsEnabled) {
        $systemPrompt .= "\n\nJelenleg az Unforgettable HTTP toolok nincsenek publikus URL-hez kötve. Ilyenkor csak beszélgetős/archivista szerepben működj, és jelezd röviden, hogy a külső művelethez publikus app URL szükséges.";
    }

    $conversationConfig = [
        'agent' => [
            'language' => (string) ($blueprint['language'] ?? 'hu'),
            'prompt' => [
                'prompt' => $systemPrompt,
                'llm' => 'gpt-5.2',
                'tools' => array_merge([
                    ['type' => 'system', 'name' => 'end_call', 'description' => 'Beszélgetés lezárása, ha a felhasználó egyértelműen befejezte.'],
                ], $toolsEnabled ? build_agent_tools($publicBaseUrl) : []),
                'knowledge_base' => [],
                'temperature' => 0.35,
                'max_tokens' => 900,
            ],
            'first_message' => (string) ($personality['first_message'] ?? 'Itt vagyok. Mondd, amit menteni, keresni vagy továbbvinni szeretnél.'),
            'dynamic_variables' => ['dynamic_variable_placeholders' => (object) []],
        ],
        'asr' => [
            'quality' => 'high',
            'provider' => 'elevenlabs',
            'user_input_audio_format' => 'pcm_16000',
            'keywords' => ['Unforgettable', 'tuti mentsd el', 'új versszak', 'olvasd vissza', 'nézz utána'],
        ],
        'tts' => [
            'voice_id' => trim((string) ($settings['elevenlabs_voice_id'] ?? '')) ?: 'pNInz6obpgDQGcFmaJgB',
            'model_id' => trim((string) ($settings['elevenlabs_tts_model_id'] ?? '')) ?: 'eleven_multilingual_v2',
            'agent_output_audio_format' => 'pcm_16000',
            'optimize_streaming_latency' => 3,
            'stability' => (float) ($settings['elevenlabs_stability'] ?? 0.5),
            'similarity_boost' => (float) ($settings['elevenlabs_similarity_boost'] ?? 0.75),
        ],
        'turn' => ['turn_timeout' => 18],
        'conversation' => [
            'max_duration_seconds' => 1800,
            'client_events' => ['audio', 'interruption', 'user_transcript', 'agent_response', 'agent_response_correction'],
        ],
        'language_presets' => (object) [],
        'is_blocked_ivc' => false,
        'is_blocked_non_ivc' => false,
    ];

    $platformSettings = [
        'widget' => [
            'variant' => 'full',
            'feedback_mode' => 'during',
            'show_avatar_when_collapsed' => true,
        ],
        'evaluation' => (object) [],
        'auth' => ['allowlist' => []],
        'overrides' => (object) [],
        'call_limits' => ['agent_concurrency_limit' => -1, 'daily_limit' => 1000],
        'privacy' => [
            'record_voice' => false,
            'retention_days' => 30,
            'delete_transcript_and_pii' => false,
            'delete_audio' => true,
            'apply_to_existing_conversations' => false,
        ],
        'data_collection' => (object) [],
    ];

    $payload = [
        'name' => (string) ($blueprint['agent_name'] ?? 'Unforgettable Archivista'),
        'conversation_config' => $conversationConfig,
        'platform_settings' => $platformSettings,
    ];

    return $payload;
}

function create_agent_with_llm_fallbacks(array $payload): array
{
    $llms = ['gpt-5.2', 'gemini-2.5-flash', 'gemini-2.0-flash-001'];
    $lastError = '';
    foreach ($llms as $llm) {
        $payload['conversation_config']['agent']['prompt']['llm'] = $llm;
        try {
            $response = elevenlabs_json('POST', '/v1/convai/agents/create', $payload);
            $response['llm'] = $llm;
            return $response;
        } catch (Throwable $error) {
            $lastError = app_redact_secrets($error->getMessage());
        }
    }
    throw new RuntimeException('Nem sikerült létrehozni az ElevenLabs agentet: ' . $lastError);
}

function build_agent_tools(string $publicBaseUrl): array
{
    $url = $publicBaseUrl . '/api/elevenlabs-agent-tool.php';
    return [
        webhook_tool($url, 'search_archive', 'Keresés az Unforgettable session archívumban.', [
            'action' => ['type' => 'string', 'enum' => ['search_archive'], 'description' => 'Mindig search_archive.'],
            'query' => ['type' => 'string', 'description' => 'A keresett gondolat, motívum, verssor vagy téma.'],
            'limit' => ['type' => 'integer', 'description' => 'Találatok száma, legfeljebb 10.'],
        ], ['action', 'query']),
        webhook_tool($url, 'get_session', 'Konkrét Unforgettable session tartalmának lekérése.', [
            'action' => ['type' => 'string', 'enum' => ['get_session'], 'description' => 'Mindig get_session.'],
            'session_id' => ['type' => 'string', 'description' => 'Az Unforgettable session azonosítója.'],
        ], ['action', 'session_id']),
        webhook_tool($url, 'save_memory', 'Új gondolat vagy beszélgetés mentése sessionként.', [
            'action' => ['type' => 'string', 'enum' => ['save_memory'], 'description' => 'Mindig save_memory.'],
            'title' => ['type' => 'string', 'description' => 'Rövid cím, ha adható.'],
            'text' => ['type' => 'string', 'description' => 'A mentendő gondolat vagy beszélgetésrész.'],
            'important' => ['type' => 'boolean', 'description' => 'Igaz, ha a felhasználó fontosként jelölte.'],
        ], ['action', 'text']),
        webhook_tool($url, 'append_memory', 'Meglévő session folytatása.', [
            'action' => ['type' => 'string', 'enum' => ['append_memory'], 'description' => 'Mindig append_memory.'],
            'session_id' => ['type' => 'string', 'description' => 'A folytatandó session azonosítója.'],
            'text' => ['type' => 'string', 'description' => 'Az újonnan hozzáadandó szöveg.'],
            'important' => ['type' => 'boolean', 'description' => 'Igaz, ha fontosként jelölt folytatás.'],
        ], ['action', 'session_id', 'text']),
        webhook_tool($url, 'prepare_email', 'Session email export előkészítése vagy küldése.', [
            'action' => ['type' => 'string', 'enum' => ['prepare_email'], 'description' => 'Mindig prepare_email.'],
            'session_id' => ['type' => 'string', 'description' => 'A küldendő session azonosítója.'],
            'to' => ['type' => 'string', 'description' => 'Opcionális címzett email.'],
        ], ['action', 'session_id']),
        webhook_tool($url, 'prepare_google_doc', 'Session Google Docs dokumentum létrehozása vagy előkészítése.', [
            'action' => ['type' => 'string', 'enum' => ['prepare_google_doc'], 'description' => 'Mindig prepare_google_doc.'],
            'session_id' => ['type' => 'string', 'description' => 'A dokumentumba küldendő session azonosítója.'],
        ], ['action', 'session_id']),
        webhook_tool($url, 'send_openai_summary', 'Session összefoglaló küldése OpenAI-ba.', [
            'action' => ['type' => 'string', 'enum' => ['send_openai_summary'], 'description' => 'Mindig send_openai_summary.'],
            'session_id' => ['type' => 'string', 'description' => 'Az összefoglalandó session azonosítója.'],
        ], ['action', 'session_id']),
    ];
}

function webhook_tool(string $url, string $name, string $description, array $properties, array $required): array
{
    return [
        'type' => 'webhook',
        'name' => $name,
        'description' => $description,
        'api_schema' => [
            'url' => $url,
            'method' => 'POST',
            'path_params_schema' => [],
            'query_params_schema' => [],
            'request_body_schema' => [
                'type' => 'object',
                'properties' => $properties,
                'required' => $required,
            ],
            'request_headers' => [
                'Authorization' => 'Bearer ' . elevenlabs_agent_tool_secret(),
                'Content-Type' => 'application/json',
            ],
        ],
    ];
}
