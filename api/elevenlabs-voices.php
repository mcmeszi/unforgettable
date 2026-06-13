<?php
require dirname(__DIR__) . '/app/bootstrap.php';
require dirname(__DIR__) . '/app/elevenlabs.php';
require_login();

$query = trim((string) ($_GET['q'] ?? ''));
try {
    json_response(['ok' => true, 'voices' => elevenlabs_search_voices($query)]);
} catch (Throwable $error) {
    json_response(['ok' => false, 'error' => $error->getMessage()], 502);
}
