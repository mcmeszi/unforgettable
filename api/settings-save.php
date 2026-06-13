<?php
require dirname(__DIR__) . '/app/bootstrap.php';
require_login();

$settings = save_app_settings(request_json());
json_response(['ok' => true, 'settings' => public_app_settings($settings)]);
