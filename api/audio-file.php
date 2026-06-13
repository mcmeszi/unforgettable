<?php
require dirname(__DIR__) . '/app/bootstrap.php';
require_login();

$file = preg_replace('/[^a-zA-Z0-9_.-]/', '', basename((string) ($_GET['file'] ?? ''))) ?: '';
if ($file === '') {
    http_response_code(404);
    exit;
}
$path = data_path('audio/' . $file);
if (!is_file($path) || !str_starts_with((string) realpath($path), (string) realpath(data_path('audio')))) {
    http_response_code(404);
    exit;
}

header('Content-Type: audio/mpeg');
header('Content-Length: ' . filesize($path));
header('Cache-Control: private, max-age=3600');
readfile($path);
