<?php
require dirname(__DIR__) . '/app/bootstrap.php';
require_login();
$session = read_session((string) ($_GET['id'] ?? ''));
if (!$session) { http_response_code(404); exit('Not found'); }
header('Content-Type: text/plain; charset=utf-8');
header('Content-Disposition: attachment; filename="' . safe_id((string) $session['id']) . '.txt"');
echo transcript_for_session($session);
