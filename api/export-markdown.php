<?php
require dirname(__DIR__) . '/app/bootstrap.php';
require_login();
$session = read_session((string) ($_GET['id'] ?? ''));
if (!$session) { http_response_code(404); exit('Not found'); }
$latest = latest_output($session);
header('Content-Type: text/markdown; charset=utf-8');
header('Content-Disposition: attachment; filename="' . safe_id((string) $session['id']) . '.md"');
echo (string) ($latest['markdown'] ?? '');
