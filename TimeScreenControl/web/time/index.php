<?php
header('Content-Type: text/html; charset=utf-8');
?><!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#172554"><meta name="robots" content="noindex,nofollow"><link rel="manifest" href="manifest.webmanifest"><link rel="stylesheet" href="app.css"><title>TimeScreen Family</title></head>
<body><header><div><strong>TimeScreen</strong><span>Family для ПК</span></div><button id="logout" class="ghost hidden">Выйти</button></header>
<main>
 <section id="auth" class="auth-shell">
  <form id="auth-form" class="card auth-card">
   <div class="mode-switch" role="tablist" aria-label="Режим авторизации"><button id="mode-login" type="button" class="active" role="tab" aria-selected="true">Вход</button><button id="mode-register" type="button" role="tab" aria-selected="false">Регистрация</button></div>
   <h1 id="auth-title">Вход</h1><p id="auth-hint">Сессия сохранится на этом устройстве на 30 дней.</p>
   <label>Email<input name="email" type="email" autocomplete="email" required></label>
   <label><span id="password-label">Пароль</span><input id="auth-password" name="password" type="password" autocomplete="current-password" required></label>
   <div class="auth-actions"><button id="auth-submit">Войти</button><button id="resend-verification" type="button" class="secondary hidden">Отправить письмо повторно</button></div>
  </form>
 </section>
 <section id="dashboard" class="hidden">
  <div class="toolbar"><div><h1>Мои компьютеры</h1><p id="account"></p></div><button id="add-device">Добавить устройство</button></div>
  <div id="device-list" class="device-grid"></div>
 </section>
</main>
<footer>TimeScreen Control · Alex · <a href="https://k-alex.ru">k-alex.ru</a> · <a href="https://k-alex.ru/legal/">Политика конфиденциальности</a></footer>
<dialog id="pair-dialog"><form method="dialog" class="card"><button class="close" value="cancel">×</button><h2>Связать компьютер</h2><p>Откройте на ПК «Настройки → Связывание» и введите текущий шестизначный код.</p><label>Код<input id="pair-code" inputmode="numeric" maxlength="6" pattern="[0-9]{6}" placeholder="000000"></label><button id="pair-submit" type="button">Связать</button></form></dialog>
<dialog id="device-dialog"><form id="device-form" method="dialog" class="card wide"><button class="close" value="cancel">×</button><h2 id="device-title"></h2><input id="device-id" type="hidden"><div id="online"></div>
 <fieldset><legend>Защита</legend><label class="check"><input id="enabled" type="checkbox"> Включена</label><label class="check"><input id="show-timer" type="checkbox"> Показывать таймер</label></fieldset>
 <fieldset><legend>Контролируемые пользователи</legend><div id="users"></div></fieldset>
 <fieldset><legend>Разрешённые интервалы</legend><div id="intervals"></div><button id="add-interval" type="button" class="secondary">Добавить интервал</button></fieldset>
 <fieldset><legend>Регулярные перерывы</legend><label class="check"><input id="break-enabled" type="checkbox"> Включить</label><div class="row"><label>Работа, минут<input id="work-minutes" type="number" min="1" max="1440"></label><label>Перерыв, минут<input id="break-minutes" type="number" min="1" max="180"></label></div></fieldset>
 <div class="actions"><button type="submit">Сохранить</button><button id="unlink" type="button" class="danger">Отвязать</button></div>
 </form></dialog>
<div id="toast" role="status"></div><script src="app.js" defer></script></body></html>
