<?php
require dirname(__DIR__) . '/app/bootstrap.php';
require_login();

$data = request_json();
$query = trim((string) ($data['query'] ?? ''));
$sessionId = trim((string) ($data['id'] ?? ''));
$session = $sessionId !== '' ? read_session($sessionId) : null;
if ($query === '') {
    json_response(['ok' => false, 'error' => 'Hiányzó kutatási kérdés.'], 422);
}
if ($sessionId !== '' && !$session) {
    json_response(['ok' => false, 'error' => 'Session nem található a kutatás mentéséhez.'], 404);
}

$results = [
    ['title' => 'Top 3 gyors válasz', 'summary' => 'Külső keresőkulcs nélkül ez egy helyi research jegyzet. Add meg a forrásokat vagy konfigurálj kereső API-t.', 'source' => 'local'],
    ['title' => 'Sessionbe mentve', 'summary' => 'A kérdés és a top-3 blokk bekerül a session output Kutatások részébe.', 'source' => 'local'],
    ['title' => 'Flow megőrzés', 'summary' => 'A válasz rövid marad, nem indít proaktív beszélgetést.', 'source' => 'local'],
];

$item = ['query' => $query, 'created_at' => now_iso(), 'results' => $results];
file_put_contents(data_path('research/' . make_id('research') . '.json'), json_encode($item, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT));
if ($session) {
    $session['research'][] = $item;
    $session['updated_at'] = now_iso();
    write_session($session);
}
json_response(['ok' => true, 'research' => $item]);
