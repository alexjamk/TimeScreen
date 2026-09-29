<?php
declare(strict_types=1);
require __DIR__ . '/bootstrap.php';
$token=(string)($_GET['token']??''); $ok=false;
if($token){$stmt=db()->prepare('UPDATE users SET verified_at=?,verify_hash=NULL,verify_expires=NULL WHERE verify_hash=? AND verify_expires>=? AND verified_at IS NULL'); $stmt->execute([time(),token_hash($token),time()]); $ok=$stmt->rowCount()===1;}
header('Content-Type: text/html; charset=utf-8'); header("Content-Security-Policy: default-src 'none'; style-src 'self'; base-uri 'none'; frame-ancestors 'none'");
?><!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><link rel="stylesheet" href="app.css"><title>TimeScreen</title></head><body><main class="card verify"><h1><?= $ok?'Email подтверждён':'Ссылка недействительна' ?></h1><p><?= $ok?'Теперь можно войти в TimeScreen.':'Возможно, ссылка истекла или уже использована.' ?></p><a class="button" href="./">Открыть приложение</a></main></body></html>
