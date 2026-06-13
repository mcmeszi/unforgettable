<?php

declare(strict_types=1);

define('APP_NAME', 'Unforgettable');
define('APP_TIMEZONE', 'Europe/Budapest');
define('APP_ROOT', dirname(__DIR__));
define('DATA_ROOT', APP_ROOT . '/data');
define('EXPORT_ROOT', APP_ROOT . '/exports');

date_default_timezone_set(APP_TIMEZONE);

return [
    'app_name' => APP_NAME,
    'timezone' => APP_TIMEZONE,
    'digest_hour' => '08:00',
];
