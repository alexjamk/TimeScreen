<?php
declare(strict_types=1);
require __DIR__ . '/bootstrap.php';

try {
    $action=(string)($_GET['action']??''); $method=$_SERVER['REQUEST_METHOD']??'GET';
    if(strlen($action)>40||!preg_match('/^[a-z-]*$/',$action)) error_response('Маршрут не найден',404);
    if($method==='OPTIONS') json_response(['ok'=>true]);
    if($action==='health' && $method==='GET'){
        db();
        json_response(['ok'=>true,'database_driver'=>in_array('sqlite',PDO::getAvailableDrivers(),true)?'pdo_sqlite':'sqlite3']);
    }

    if($action==='register' && $method==='POST'){
        $data=json_input(); $email=text_lower(trim((string)($data['email']??''))); $password=(string)($data['password']??'');
        rate_limit('register-ip',client_ip(),5,3600);
        if(!filter_var($email,FILTER_VALIDATE_EMAIL)||strlen($email)>254) error_response('Некорректный email');
        rate_limit('register-account',$email,3,86400);
        $passwordLength=text_length($password);
        if($passwordLength<7||$passwordLength>256) error_response('Пароль должен содержать не менее 7 символов');
        $verify=random_token(); $db=db();
        try{$db->prepare('INSERT INTO users(email,password_hash,verify_hash,verify_expires,created_at) VALUES(?,?,?,?,?)')->execute([$email,password_hash($password,PASSWORD_DEFAULT),token_hash($verify),time()+86400,time()]);}
        catch(Throwable $e){error_response('Аккаунт уже существует. Если email не подтверждён, отправьте письмо повторно.',409);}
        $url=cfg()['base_url'].'/verify.php?token='.rawurlencode($verify);
        if(!send_verification_mail($email,$url)){$db->prepare('DELETE FROM users WHERE email=? AND verified_at IS NULL')->execute([$email]); error_response('Не удалось отправить письмо. Повторите позже.',503);}
        audit(null,null,'register'); json_response(['ok'=>true,'message'=>'Письмо для подтверждения отправлено'],201);
    }

    if($action==='resend-verification' && $method==='POST'){
        $data=json_input(); $email=text_lower(trim((string)($data['email']??'')));
        rate_limit('resend-ip',client_ip(),10,3600);
        if(!filter_var($email,FILTER_VALIDATE_EMAIL)||strlen($email)>254) error_response('Некорректный email');
        rate_limit('resend-account',$email,3,3600);
        $stmt=db()->prepare('SELECT id FROM users WHERE email=? AND verified_at IS NULL'); $stmt->execute([$email]); $user=$stmt->fetch();
        if($user){
            $verify=random_token(); $url=cfg()['base_url'].'/verify.php?token='.rawurlencode($verify);
            if(!send_verification_mail($email,$url)) error_response('Не удалось отправить письмо. Повторите позже.',503);
            db()->prepare('UPDATE users SET verify_hash=?,verify_expires=? WHERE id=?')->execute([token_hash($verify),time()+86400,$user['id']]);
            audit((int)$user['id'],null,'resend-verification');
        }
        json_response(['ok'=>true,'message'=>'Если адрес ожидает подтверждения, новое письмо отправлено']);
    }

    if($action==='login' && $method==='POST'){
        $data=json_input(); $email=text_lower(trim((string)($data['email']??''))); $password=(string)($data['password']??'');
        rate_limit('login-ip',client_ip(),30,900);
        if(strlen($email)>254||text_length($password)>256) error_response('Неверный email или пароль',401);
        rate_limit('login-account',$email,10,900);
        $stmt=db()->prepare('SELECT * FROM users WHERE email=?'); $stmt->execute([$email]); $user=$stmt->fetch();
        $hash=$user?$user['password_hash']:'$2y$10$Rnu4NQ4h/Seqsm4COBzmQe8Xj2uIp7DTPugjni6amTOuCRERvEmUm';
        $valid=password_verify($password,$hash);
        if(!$user||!$valid||!$user['verified_at']) error_response('Неверный email или пароль, либо email не подтверждён',401);
        if(password_needs_rehash($user['password_hash'],PASSWORD_DEFAULT)) db()->prepare('UPDATE users SET password_hash=? WHERE id=?')->execute([password_hash($password,PASSWORD_DEFAULT),$user['id']]);
        db()->prepare('DELETE FROM sessions WHERE user_id=? AND token_hash NOT IN (SELECT token_hash FROM sessions WHERE user_id=? ORDER BY created_at DESC LIMIT 4)')->execute([$user['id'],$user['id']]);
        $session=random_token(); $csrf=random_token(); db()->prepare('INSERT INTO sessions(token_hash,user_id,csrf_hash,expires_at,created_at) VALUES(?,?,?,?,?)')->execute([token_hash($session),$user['id'],token_hash($csrf),time()+2592000,time()]);
        set_session_cookie($session); audit((int)$user['id'],null,'login'); json_response(['ok'=>true,'csrf'=>$csrf,'email'=>$user['email']]);
    }

    if($action==='logout' && $method==='POST'){
        $user=current_user(true); $token=$_COOKIE[SESSION_COOKIE]??''; db()->prepare('DELETE FROM sessions WHERE token_hash=?')->execute([token_hash($token)]);
        setcookie(SESSION_COOKIE,'',['expires'=>1,'path'=>'/','secure'=>true,'httponly'=>true,'samesite'=>'Strict']); audit((int)$user['id'],null,'logout'); json_response(['ok'=>true]);
    }

    if($action==='me' && $method==='GET'){
        $user=current_user(); $csrf=random_token(); $session=$_COOKIE[SESSION_COOKIE]??'';
        db()->prepare('UPDATE sessions SET csrf_hash=? WHERE token_hash=?')->execute([token_hash($csrf),token_hash($session)]);
        json_response(['ok'=>true,'email'=>$user['email'],'csrf'=>$csrf]);
    }

    if($action==='device-register' && $method==='POST'){
        $data=json_input();
        $id=(string)($data['device_id']??''); $token=(string)($data['token']??''); $name=text_limit(trim((string)($data['name']??'Компьютер')),100); $platform=text_limit(trim((string)($data['platform']??'Windows')),100);
        if(!preg_match('/^[a-f0-9]{8}-[a-f0-9]{4}-[1-5][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/',$id)||!preg_match('/^[A-Za-z0-9_-]{32,128}$/',$token)) error_response('Некорректные данные устройства');
        $stmt=db()->prepare('SELECT token_hash FROM devices WHERE id=?'); $stmt->execute([$id]); $existing=$stmt->fetch();
        if($existing && !hash_equals($existing['token_hash'],token_hash($token))) error_response('Устройство уже зарегистрировано',409);
        if(!$existing) rate_limit('device-register-ip',client_ip(),20,3600);
        // Versions up to 3.7 refreshed registration every 20 seconds. Keep a
        // compatibility ceiling while newer clients register only once.
        else rate_limit('device-register-id',$id,240,3600);
        db()->prepare('INSERT INTO devices(id,token_hash,name,platform,created_at) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,platform=excluded.platform')->execute([$id,token_hash($token),$name,$platform,time()]);
        json_response(['ok'=>true]);
    }

    if($action==='device-pair-code' && $method==='POST'){
        $device=device_auth(); $data=json_input(); $code=(string)($data['code']??'');
        if(!preg_match('/^\d{6}$/',$code)) error_response('Некорректный код');
        db()->prepare('UPDATE devices SET pairing_hash=?,pairing_expires=?,last_seen_at=? WHERE id=?')->execute([token_hash('pair:'.$code),time()+90,time(),$device['id']]);
        json_response(['ok'=>true,'paired'=>(bool)$device['owner_user_id']]);
    }

    if($action==='pair' && $method==='POST'){
        $user=current_user(true); $data=json_input(); $code=(string)($data['code']??'');
        rate_limit('pair-user',(string)$user['id'],5,900); rate_limit('pair-ip',client_ip(),20,900);
        $count=db()->prepare('SELECT COUNT(*) FROM devices WHERE owner_user_id=?'); $count->execute([$user['id']]);
        if((int)$count->fetchColumn()>=3) error_response('Можно связать не более трёх устройств',409);
        if(!preg_match('/^\d{6}$/',$code)) error_response('Код не найден или истёк',404);
        $stmt=db()->prepare('SELECT * FROM devices WHERE pairing_hash=? AND pairing_expires>=? AND owner_user_id IS NULL'); $stmt->execute([token_hash('pair:'.$code),time()]); $matches=$stmt->fetchAll();
        if(count($matches)!==1) error_response('Код не найден или истёк',404);
        $device=$matches[0]; db()->prepare('UPDATE devices SET owner_user_id=?,pairing_hash=NULL,pairing_expires=NULL WHERE id=?')->execute([$user['id'],$device['id']]);
        audit((int)$user['id'],$device['id'],'pair'); json_response(['ok'=>true,'device_id'=>$device['id']]);
    }

    if($action==='devices' && $method==='GET'){
        $user=current_user(); $stmt=db()->prepare('SELECT id,name,platform,last_seen_at,config_json,config_revision,available_users_json,user_statuses_json FROM devices WHERE owner_user_id=? ORDER BY name'); $stmt->execute([$user['id']]);
        $items=[]; foreach($stmt as $row){$row['config']=$row['config_json']?json_decode($row['config_json'],true):null; $row['available_users']=json_decode($row['available_users_json'],true)?:[]; $row['user_statuses']=json_decode($row['user_statuses_json'],true)?:[]; unset($row['config_json'],$row['available_users_json'],$row['user_statuses_json']); $items[]=$row;}
        json_response(['ok'=>true,'devices'=>$items,'server_time'=>time()]);
    }

    if($action==='device-config' && $method==='POST'){
        $user=current_user(true); $data=json_input(); $id=(string)($data['device_id']??''); $settings=validate_settings($data['config']??null);
        $stmt=db()->prepare('UPDATE devices SET config_json=?,config_revision=config_revision+1,config_updated_at=? WHERE id=? AND owner_user_id=?'); $stmt->execute([json_encode($settings,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES),time(),$id,$user['id']]);
        if($stmt->rowCount()!==1) error_response('Устройство не найдено',404); audit((int)$user['id'],$id,'config-update'); json_response(['ok'=>true]);
    }

    if($action==='grant-time' && $method==='POST'){
        $user=current_user(true); $data=json_input(); $id=(string)($data['device_id']??''); $username=text_limit(trim((string)($data['username']??'')),128); $minutes=filter_var($data['minutes']??null,FILTER_VALIDATE_INT,['options'=>['min_range'=>1,'max_range'=>180]]); if($minutes===false) error_response('Допустимо от 1 до 180 минут');
        $stmt=db()->prepare('SELECT available_users_json FROM devices WHERE id=? AND owner_user_id=?'); $stmt->execute([$id,$user['id']]); $device=$stmt->fetch(); if(!$device) error_response('Устройство не найдено',404);
        $available=json_decode($device['available_users_json'],true)?:[]; if(!$username||!in_array($username,$available,true)) error_response('Пользователь не найден на устройстве',404);
        $now=time(); db()->prepare('INSERT INTO commands(device_id,type,payload_json,created_at,expires_at) VALUES(?,?,?,?,?)')->execute([$id,'grant-time',json_encode(['minutes'=>$minutes,'username'=>$username],JSON_UNESCAPED_UNICODE),$now,$now+3600]); audit((int)$user['id'],$id,'grant-time'); json_response(['ok'=>true]);
    }

    if($action==='unlink' && $method==='POST'){
        $user=current_user(true); $data=json_input(); $id=(string)($data['device_id']??'');
        $stmt=db()->prepare('UPDATE devices SET owner_user_id=NULL,config_json=NULL,config_revision=0,pairing_hash=NULL,pairing_expires=NULL WHERE id=? AND owner_user_id=?'); $stmt->execute([$id,$user['id']]); if($stmt->rowCount()!==1) error_response('Устройство не найдено',404); audit((int)$user['id'],$id,'unlink'); json_response(['ok'=>true]);
    }

    if($action==='device-sync' && $method==='POST'){
        $device=device_auth(); $data=json_input(); $known=max(0,(int)($data['known_revision']??0)); $localDirty=(bool)($data['local_dirty']??false); $settings=validate_settings($data['config']??null); $users=array_slice(array_values(array_unique(array_map(fn($v)=>text_limit(trim((string)$v),128),$data['available_users']??[]))),0,64); $statuses=validate_user_statuses($data['user_statuses']??[],$users); $db=db(); $db->beginTransaction();
        $stmt=$db->prepare('SELECT * FROM devices WHERE id=?'); $stmt->execute([$device['id']]); $fresh=$stmt->fetch(); $serverRevision=(int)$fresh['config_revision'];
        if(!$fresh['config_json'] || ($known===$serverRevision && $localDirty)){$serverRevision++; $db->prepare('UPDATE devices SET config_json=?,config_revision=?,config_updated_at=? WHERE id=?')->execute([json_encode($settings,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES),$serverRevision,time(),$device['id']]); $remote=$settings;} else {$remote=json_decode($fresh['config_json'],true);}
        $db->prepare('UPDATE devices SET available_users_json=?,user_statuses_json=?,last_seen_at=? WHERE id=?')->execute([json_encode($users,JSON_UNESCAPED_UNICODE),json_encode($statuses,JSON_UNESCAPED_UNICODE),time(),$device['id']]);
        $cmd=$db->prepare("SELECT id,type,payload_json FROM commands WHERE device_id=? AND status IN ('pending','delivered') AND (expires_at IS NULL OR expires_at>=?) ORDER BY id LIMIT 10"); $cmd->execute([$device['id'],time()]); $commands=$cmd->fetchAll();
        foreach($commands as &$c){$c['payload']=json_decode($c['payload_json'],true); unset($c['payload_json']); $db->prepare("UPDATE commands SET status='delivered',delivered_at=? WHERE id=?")->execute([time(),$c['id']]);}
        $db->commit(); json_response(['ok'=>true,'paired'=>(bool)$fresh['owner_user_id'],'revision'=>$serverRevision,'config'=>$remote,'commands'=>$commands]);
    }

    if($action==='device-ack' && $method==='POST'){
        $device=device_auth(); $data=json_input(); $ids=array_slice(array_map('intval',$data['command_ids']??[]),0,20); if($ids){$marks=implode(',',array_fill(0,count($ids),'?')); db()->prepare("UPDATE commands SET status='done' WHERE device_id=? AND id IN ($marks)")->execute(array_merge([$device['id']],$ids));} json_response(['ok'=>true]);
    }

    if($action==='device-revoke' && $method==='POST'){
        $device=device_auth();
        if($device['owner_user_id']!==null) error_response('Сначала отвяжите устройство в личном кабинете',409);
        db()->prepare('DELETE FROM devices WHERE id=?')->execute([$device['id']]);
        json_response(['ok'=>true]);
    }

    error_response('Маршрут не найден',404);
} catch(Throwable $e) {
    error_log('TimeScreen API: '.$e->getMessage()); error_response('Внутренняя ошибка сервера',500);
}
