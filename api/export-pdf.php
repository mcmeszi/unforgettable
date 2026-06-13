<?php
require dirname(__DIR__) . '/app/bootstrap.php';
require_login();
$session = read_session((string) ($_GET['id'] ?? ''));
if (!$session) { http_response_code(404); exit('Not found'); }
$latest = latest_output($session);
header('Content-Type: text/html; charset=utf-8');
header('Content-Disposition: attachment; filename="' . safe_id((string) $session['id']) . '.html"');
echo '<!doctype html><meta charset="utf-8"><title>' . htmlspecialchars((string) $session['title']) . '</title><body onload="window.print()"><pre style="font:15px/1.55 system-ui;white-space:pre-wrap;max-width:760px;margin:48px auto">' . htmlspecialchars((string) ($latest['markdown'] ?? '')) . '</pre>';
