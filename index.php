<?php
require __DIR__ . '/app/bootstrap.php';
header('Location: ' . (is_logged_in() ? '/app/index.php' : '/app/login.php'));
exit;
