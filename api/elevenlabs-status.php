<?php
require dirname(__DIR__) . '/app/bootstrap.php';
require dirname(__DIR__) . '/app/elevenlabs.php';
require_login();

json_response(['ok' => true, 'elevenlabs' => elevenlabs_status()]);
