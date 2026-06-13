<?php
require dirname(__DIR__) . '/app/bootstrap.php';
require_login();

json_response(['ok' => true, 'setup' => app_setup_status()]);
