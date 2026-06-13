<?php

declare(strict_types=1);

$defaults = [
    'password_hash' => '$2y$12$au0Bb5LoMNXcAQKX.ZCjyu6bhng24G60ndHJUuEkjAPvNVXLUQlk.',
    'openai_api_key' => getenv('OPENAI_API_KEY') ?: '',
    'openai_model' => getenv('OPENAI_MODEL') ?: 'gpt-4.1',
    'openai_summary_model' => getenv('OPENAI_SUMMARY_MODEL') ?: 'gpt-4.1',
    'search_api_key' => '',
    'elevenlabs_api_key' => getenv('ELEVENLABS_API_KEY') ?: '',
    'elevenlabs_agent_tool_secret' => getenv('ELEVENLABS_AGENT_TOOL_SECRET') ?: '',
    'elevenlabs_webhook_secret' => getenv('ELEVENLABS_WEBHOOK_SECRET') ?: '',
    'public_base_url' => getenv('UNFORGETTABLE_PUBLIC_BASE_URL') ?: '',
    'drive_enabled' => false,
    'email_enabled' => false,
    'email_default_to' => getenv('UNFORGETTABLE_EMAIL_TO') ?: '',
    'email_from' => getenv('UNFORGETTABLE_EMAIL_FROM') ?: 'unforgettable@localhost',
    'google_docs_enabled' => false,
    'google_docs_folder_id' => getenv('GOOGLE_DOCS_FOLDER_ID') ?: '',
    'google_docs_access_token' => getenv('GOOGLE_DOCS_ACCESS_TOKEN') ?: '',
    'google_docs_refresh_token' => getenv('GOOGLE_DOCS_REFRESH_TOKEN') ?: '',
    'google_docs_client_id' => getenv('GOOGLE_DOCS_CLIENT_ID') ?: '',
    'google_docs_client_secret' => getenv('GOOGLE_DOCS_CLIENT_SECRET') ?: '',
    'google_docs_service_account_json' => getenv('GOOGLE_DOCS_SERVICE_ACCOUNT_JSON') ?: '',
    'google_docs_service_account_json_path' => getenv('GOOGLE_DOCS_SERVICE_ACCOUNT_JSON_PATH') ?: '',
    'notes_shortcut_url' => 'shortcuts://run-shortcut?name=Unforgettable%20Notes',
];

$localFile = __DIR__ . '/local.secrets.php';
if (!is_file($localFile)) {
    return $defaults;
}

$local = require $localFile;
if (!is_array($local)) {
    return $defaults;
}

$local = array_filter($local, fn ($value) => $value !== '' && $value !== null);
return array_merge($defaults, $local);
