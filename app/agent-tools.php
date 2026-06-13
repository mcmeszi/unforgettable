<?php

declare(strict_types=1);

function require_elevenlabs_agent_auth(): void
{
    $secret = elevenlabs_agent_tool_secret();
    if ($secret === '') {
        json_response(['ok' => false, 'error' => 'ElevenLabs agent tool secret nincs beállítva.'], 503);
    }

    $authorization = request_header('Authorization');
    $bearer = preg_match('/^Bearer\s+(.+)$/i', $authorization, $matches) ? trim($matches[1]) : '';
    $custom = request_header('X-Unforgettable-Tool-Secret');
    $provided = $bearer !== '' ? $bearer : $custom;

    if ($provided === '' || !hash_equals($secret, $provided)) {
        json_response(['ok' => false, 'error' => 'Nincs jogosultság az ElevenLabs agent tool használatához.'], 401);
    }
}

function session_search_blob(array $session): string
{
    $latest = latest_output($session);
    $parts = implode("\n", array_map(
        fn ($part) => (string) ($part['raw_transcript'] ?? '') . "\n" . (string) ($part['clean_transcript'] ?? ''),
        $session['parts'] ?? []
    ));
    return implode("\n", [
        (string) ($session['title'] ?? ''),
        (string) ($latest['summary'] ?? ''),
        (string) ($latest['markdown'] ?? ''),
        $parts,
    ]);
}

function snippet_for_query(string $text, string $query): string
{
    $clean = trim(preg_replace('/\s+/u', ' ', $text) ?? $text);
    if ($clean === '') {
        return '';
    }
    $needle = app_lower($query);
    $haystack = app_lower($clean);
    $pos = $needle !== '' ? strpos($haystack, $needle) : false;
    if ($pos === false) {
        return app_strlen($clean) > 220 ? app_substr($clean, 0, 217) . '...' : $clean;
    }
    $start = max(0, $pos - 90);
    $snippet = app_substr($clean, $start, 220);
    return ($start > 0 ? '...' : '') . (app_strlen($snippet) >= 220 ? app_substr($snippet, 0, 217) . '...' : $snippet);
}

function search_unforgettable_archive(string $query, int $limit = 5): array
{
    $query = trim($query);
    $limit = max(1, min(10, $limit));
    $sessions = list_sessions();
    $terms = array_values(array_filter(preg_split('/\s+/u', app_lower($query)) ?: []));
    $ranked = [];

    foreach ($sessions as $session) {
        $blob = session_search_blob($session);
        $lower = app_lower($blob);
        $score = $query === '' ? 1 : 0;
        foreach ($terms as $term) {
            if ($term === '') {
                continue;
            }
            $score += substr_count($lower, $term);
            if (str_contains(app_lower((string) ($session['title'] ?? '')), $term)) {
                $score += 4;
            }
        }
        if ($score <= 0) {
            continue;
        }
        $latest = latest_output($session);
        $ranked[] = [
            'score' => $score,
            'session_id' => (string) ($session['id'] ?? ''),
            'title' => (string) ($session['title'] ?? ''),
            'created_at' => (string) ($session['created_at'] ?? ''),
            'status' => (string) ($session['status'] ?? ''),
            'important' => !empty($session['important']),
            'summary' => (string) ($latest['summary'] ?? ''),
            'snippet' => snippet_for_query($blob, $query),
        ];
    }

    usort($ranked, fn ($a, $b) => ($b['score'] <=> $a['score']) ?: strcmp((string) $b['created_at'], (string) $a['created_at']));
    return array_slice($ranked, 0, $limit);
}

function save_agent_memory(string $text, string $title = '', bool $important = false): array
{
    $session = new_session_array(trim($title));
    $session['source'] = 'elevenlabs_agent';
    $session['important'] = $important;
    $session['keep_full_context'] = $important;
    $session['archive_priority'] = $important ? 'high' : 'normal';
    append_session_part($session, $text, 'elevenlabs_agent');
    $session['status'] = 'closed';
    $session['updated_at'] = now_iso();
    $output = build_output($session);
    $session['outputs'][] = $output;
    if ($title === '') {
        $session['title'] = title_from_summary($output['summary']);
    }
    $session['exports'] = write_exports($session);
    file_put_contents(data_path('outputs/' . $session['id'] . '_v' . $output['version'] . '.md'), $output['markdown']);
    write_session($session);

    return [
        'status' => 'saved',
        'session_id' => $session['id'],
        'title' => $session['title'],
        'summary' => $output['summary'],
    ];
}

function append_agent_memory(string $sessionId, string $text, bool $important = false): array
{
    $session = read_session($sessionId);
    if (!$session) {
        return ['status' => 'not_found', 'message' => 'Session nem található.'];
    }
    append_session_part($session, $text, 'elevenlabs_agent');
    if ($important) {
        $session['important'] = true;
        $session['keep_full_context'] = true;
        $session['archive_priority'] = 'high';
    }
    $session['status'] = 'continued';
    $session['updated_at'] = now_iso();
    $output = build_output($session);
    $session['outputs'][] = $output;
    $session['exports'] = write_exports($session);
    file_put_contents(data_path('outputs/' . $session['id'] . '_v' . $output['version'] . '.md'), $output['markdown']);
    write_session($session);

    return [
        'status' => 'appended',
        'session_id' => $session['id'],
        'title' => $session['title'],
        'summary' => $output['summary'],
        'version' => $output['version'],
    ];
}

function get_agent_session(string $sessionId): array
{
    $session = read_session($sessionId);
    if (!$session) {
        return ['status' => 'not_found', 'message' => 'Session nem található.'];
    }
    $latest = latest_output($session);
    return [
        'status' => 'found',
        'session_id' => (string) ($session['id'] ?? ''),
        'title' => (string) ($session['title'] ?? ''),
        'created_at' => (string) ($session['created_at'] ?? ''),
        'important' => !empty($session['important']),
        'summary' => (string) ($latest['summary'] ?? ''),
        'content' => session_share_content($session),
    ];
}

