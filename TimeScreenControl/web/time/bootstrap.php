<?php
declare(strict_types=1);

const SESSION_COOKIE = 'timescreen_session';
const MAX_JSON_BODY_BYTES = 65536;
const SCHEMA_VERSION = 4;

function security_headers(): void {
    header('X-Content-Type-Options: nosniff');
    header('Referrer-Policy: no-referrer');
    header('Permissions-Policy: camera=(), microphone=(), geolocation=()');
    header("Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; manifest-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'");
    header('Cross-Origin-Opener-Policy: same-origin');
    header('Cross-Origin-Resource-Policy: same-origin');
    header('X-Permitted-Cross-Domain-Policies: none');
    header('X-Robots-Tag: noindex, nofollow');
    if ((!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') || (int)($_SERVER['SERVER_PORT'] ?? 0) === 443) {
        header('Strict-Transport-Security: max-age=31536000');
    }
}
security_headers();

function cfg(): array {
    static $config;
    if ($config === null) {
        $path = getenv('TIMESCREEN_CONFIG') ?: (__DIR__ . '/private/config.php');
        if (!is_file($path)) throw new RuntimeException('Server is not configured');
        $config = require $path;
        if (empty($config['app_key']) || strlen((string)$config['app_key']) < 32) throw new RuntimeException('Invalid app key');
    }
    return $config;
}

final class SqliteStatement implements IteratorAggregate {
    private SQLite3Stmt $statement;
    private SQLite3 $connection;
    private SQLite3Result|false $result=false;
    private int $changes=0;
    public function __construct(SQLite3 $connection,string $sql){$this->connection=$connection;$this->statement=$connection->prepare($sql);}
    public function execute(array $params=[]): self {
        $this->statement->reset(); $this->statement->clear();
        foreach(array_values($params) as $index=>$value){
            $type=is_int($value)?SQLITE3_INTEGER:(is_float($value)?SQLITE3_FLOAT:($value===null?SQLITE3_NULL:SQLITE3_TEXT));
            $this->statement->bindValue($index+1,is_bool($value)?(int)$value:$value,$type);
        }
        $this->result=$this->statement->execute(); $this->changes=$this->connection->changes(); return $this;
    }
    public function fetch(): array|false {return $this->result?$this->result->fetchArray(SQLITE3_ASSOC):false;}
    public function fetchAll(): array {$rows=[];while(($row=$this->fetch())!==false)$rows[]=$row;return $rows;}
    public function fetchColumn(): mixed {if(!$this->result)return false;$row=$this->result->fetchArray(SQLITE3_NUM);return $row===false?false:($row[0]??false);}
    public function rowCount(): int {return $this->changes;}
    public function getIterator(): Traversable {while(($row=$this->fetch())!==false)yield $row;}
}

final class SqliteConnection {
    private SQLite3 $connection;
    public function __construct(string $path){SQLite3::enableExceptions(true);$this->connection=new SQLite3($path);}
    public function exec(string $sql): bool {return $this->connection->exec($sql);}
    public function prepare(string $sql): SqliteStatement {return new SqliteStatement($this->connection,$sql);}
    public function beginTransaction(): void {$this->connection->exec('BEGIN IMMEDIATE');}
    public function commit(): void {$this->connection->exec('COMMIT');}
}

function db(): PDO|SqliteConnection {
    static $pdo;
    if ($pdo === null) {
        if(in_array('sqlite',PDO::getAvailableDrivers(),true)){
            $pdo = new PDO('sqlite:' . cfg()['db_path'], null, null, [PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION, PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]);
        } elseif(class_exists('SQLite3')) {
            $pdo = new SqliteConnection((string)cfg()['db_path']);
        } else {
            throw new RuntimeException('SQLite extension is unavailable');
        }
        $pdo->exec('PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000');
        migrate($pdo);
    }
    return $pdo;
}

function migrate(PDO|SqliteConnection $db): void {
    $versionStatement=$db->prepare('PRAGMA user_version'); $versionStatement->execute();
    $version=(int)$versionStatement->fetchColumn();
    if($version<SCHEMA_VERSION){
    $db->exec(<<<'SQL'
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 verified_at INTEGER, verify_hash TEXT, verify_expires INTEGER, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 csrf_hash TEXT NOT NULL, expires_at INTEGER NOT NULL, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS devices (
 id TEXT PRIMARY KEY, owner_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
 token_hash TEXT NOT NULL, name TEXT NOT NULL, platform TEXT NOT NULL,
 pairing_hash TEXT, pairing_expires INTEGER, config_json TEXT, config_revision INTEGER NOT NULL DEFAULT 0,
 config_updated_at INTEGER NOT NULL DEFAULT 0, available_users_json TEXT NOT NULL DEFAULT '[]',
 user_statuses_json TEXT NOT NULL DEFAULT '[]',
 last_seen_at INTEGER, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS device_shares (
 device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 granted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
 created_at INTEGER NOT NULL,
 PRIMARY KEY(device_id,user_id)
);
CREATE INDEX IF NOT EXISTS idx_devices_pairing ON devices(pairing_hash, pairing_expires);
CREATE INDEX IF NOT EXISTS idx_devices_owner ON devices(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_device_shares_user ON device_shares(user_id);
CREATE TABLE IF NOT EXISTS commands (
 id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
 type TEXT NOT NULL, payload_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
 created_at INTEGER NOT NULL, delivered_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_commands_pending ON commands(device_id, status);
CREATE TABLE IF NOT EXISTS rate_limits (
 bucket TEXT NOT NULL, identity TEXT NOT NULL, window_start INTEGER NOT NULL, attempts INTEGER NOT NULL,
 PRIMARY KEY(bucket, identity)
);
CREATE TABLE IF NOT EXISTS audit_log (
 id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, device_id TEXT, action TEXT NOT NULL,
 ip_hash TEXT NOT NULL, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS app_meta (
 key TEXT PRIMARY KEY, value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);
SQL);
    try {$db->exec("ALTER TABLE devices ADD COLUMN user_statuses_json TEXT NOT NULL DEFAULT '[]'");}
    catch(Throwable $ignored) {}
    try {$db->exec('ALTER TABLE commands ADD COLUMN expires_at INTEGER');}
    catch(Throwable $ignored) {}
    $db->exec('PRAGMA user_version='.SCHEMA_VERSION);
    }
    run_maintenance($db);
}

function run_maintenance(PDO|SqliteConnection $db): void {
    $now=time();
    $stmt=$db->prepare("INSERT INTO app_meta(key,value) VALUES('last_maintenance',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value WHERE CAST(app_meta.value AS INTEGER)<?");
    $stmt->execute([(string)$now,$now-3600]);
    if($stmt->rowCount()!==1) return;
    $db->prepare('DELETE FROM sessions WHERE expires_at < ?')->execute([$now]);
    $db->prepare('DELETE FROM users WHERE verified_at IS NULL AND verify_expires < ?')->execute([$now]);
    $db->prepare('DELETE FROM devices WHERE owner_user_id IS NULL AND created_at < ?')->execute([$now-604800]);
    $db->prepare('DELETE FROM rate_limits WHERE window_start < ?')->execute([$now-86400]);
    $db->prepare("DELETE FROM commands WHERE (expires_at IS NOT NULL AND expires_at < ?) OR (status='done' AND created_at < ?)")->execute([$now,$now-604800]);
    $db->prepare('DELETE FROM audit_log WHERE created_at < ?')->execute([$now-7776000]);
}

function json_input(): array {
    $contentType=text_lower(trim(explode(';',$_SERVER['CONTENT_TYPE']??'',2)[0]));
    if($contentType!=='application/json') error_response('Требуется Content-Type application/json',415);
    $declared=(int)($_SERVER['CONTENT_LENGTH']??0);
    if($declared>MAX_JSON_BODY_BYTES) error_response('Запрос слишком большой',413);
    $stream=fopen('php://input','rb');
    $raw=$stream===false?'':stream_get_contents($stream,MAX_JSON_BODY_BYTES+1);
    if($stream!==false) fclose($stream);
    if($raw===false||strlen($raw)>MAX_JSON_BODY_BYTES) error_response('Запрос слишком большой',413);
    try {$data=json_decode($raw?:'{}',true,32,JSON_THROW_ON_ERROR);}
    catch(JsonException $e){error_response('Некорректный JSON',400);}
    if (!is_array($data)) error_response('Некорректный JSON',400);
    return $data;
}

function json_response(array $data, int $status = 200): never {
    http_response_code($status); header('Content-Type: application/json; charset=utf-8'); header('Cache-Control: no-store');
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES); exit;
}
function error_response(string $message, int $status = 400): never { json_response(['ok'=>false,'error'=>$message], $status); }
function random_token(int $bytes = 32): string { return rtrim(strtr(base64_encode(random_bytes($bytes)), '+/', '-_'), '='); }
function token_hash(string $value): string { return hash_hmac('sha256', $value, cfg()['app_key']); }
function client_ip(): string { return (string)($_SERVER['REMOTE_ADDR'] ?? 'unknown'); }
function client_ip_hash(): string { return token_hash(client_ip()); }
function text_lower(string $value): string { return function_exists('mb_strtolower') ? mb_strtolower($value) : strtolower($value); }
function text_limit(string $value, int $length): string {
    if(function_exists('mb_substr')) return mb_substr($value,0,$length);
    $characters=preg_split('//u',$value,-1,PREG_SPLIT_NO_EMPTY);
    return $characters===false ? substr($value,0,$length) : implode('',array_slice($characters,0,$length));
}
function text_length(string $value): int {
    if(function_exists('mb_strlen')) return mb_strlen($value);
    $count=preg_match_all('/./us',$value,$matches);
    return $count===false ? strlen($value) : $count;
}

function rate_limit(string $bucket, string $identity, int $max, int $window): void {
    $db=db(); $now=time(); $start=$now-($now%$window); $identity=token_hash($identity);
    $db->prepare('INSERT INTO rate_limits(bucket,identity,window_start,attempts) VALUES(?,?,?,1) ON CONFLICT(bucket,identity) DO UPDATE SET window_start=excluded.window_start,attempts=CASE WHEN rate_limits.window_start=excluded.window_start THEN rate_limits.attempts+1 ELSE 1 END')->execute([$bucket,$identity,$start]);
    $stmt=$db->prepare('SELECT attempts FROM rate_limits WHERE bucket=? AND identity=?'); $stmt->execute([$bucket,$identity]);
    if((int)$stmt->fetchColumn()>$max){header('Retry-After: '.max(1,$start+$window-$now)); error_response('Слишком много попыток. Повторите позже.',429);}
}

function bearer(): string {
    $header=$_SERVER['HTTP_AUTHORIZATION']??'';
    if(strlen($header)>256||!preg_match('/^Bearer\s+(.+)$/i',$header,$m)) error_response('Требуется авторизация устройства',401);
    return trim($m[1]);
}
function device_auth(): array {
    // A generous IP ceiling avoids blocking several households behind one
    // carrier NAT; the tighter per-device limit below handles abusive clients.
    rate_limit('device-auth-ip',client_ip(),1200,600);
    $parts=explode('.',bearer(),2);
    if(count($parts)!==2 || !preg_match('/^[a-f0-9]{8}-[a-f0-9]{4}-[1-5][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/',$parts[0]) || !preg_match('/^[A-Za-z0-9_-]{32,128}$/',$parts[1])) error_response('Недействительный токен устройства',401);
    $stmt=db()->prepare('SELECT * FROM devices WHERE id=?'); $stmt->execute([$parts[0]]); $row=$stmt->fetch();
    if(!$row || !hash_equals($row['token_hash'],token_hash($parts[1]))) error_response('Недействительный токен устройства',401);
    rate_limit('device-auth-id',$row['id'],150,600);
    return $row;
}

function current_user(bool $csrf=false): array {
    $token=$_COOKIE[SESSION_COOKIE]??''; if(!$token) error_response('Требуется вход',401);
    if(strlen($token)>128||!preg_match('/^[A-Za-z0-9_-]{32,128}$/',$token)) error_response('Требуется вход',401);
    $stmt=db()->prepare('SELECT u.*,s.csrf_hash FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?');
    $stmt->execute([token_hash($token),time()]); $user=$stmt->fetch(); if(!$user) error_response('Сессия истекла',401);
    if($csrf){$value=$_SERVER['HTTP_X_CSRF_TOKEN']??''; if(!$value || !hash_equals($user['csrf_hash'],token_hash($value))) error_response('Недействительный CSRF-токен',403);}
    return $user;
}
function set_session_cookie(string $token): void { setcookie(SESSION_COOKIE,$token,['expires'=>time()+2592000,'path'=>'/','secure'=>true,'httponly'=>true,'samesite'=>'Strict']); }

function accessible_device(string $deviceId,int $userId,bool $ownerOnly=false): array|false {
    if($ownerOnly){
        $stmt=db()->prepare("SELECT d.*,'owner' AS access_role FROM devices d WHERE d.id=? AND d.owner_user_id=?");
        $stmt->execute([$deviceId,$userId]);
    } else {
        $stmt=db()->prepare("SELECT DISTINCT d.*,CASE WHEN d.owner_user_id=? THEN 'owner' ELSE 'member' END AS access_role FROM devices d LEFT JOIN device_shares s ON s.device_id=d.id AND s.user_id=? WHERE d.id=? AND d.owner_user_id IS NOT NULL AND (d.owner_user_id=? OR s.user_id=?)");
        $stmt->execute([$userId,$userId,$deviceId,$userId,$userId]);
    }
    return $stmt->fetch();
}

function device_members(string $deviceId): array {
    $stmt=db()->prepare("SELECT u.id,u.email,'owner' AS role FROM devices d JOIN users u ON u.id=d.owner_user_id WHERE d.id=? UNION ALL SELECT u.id,u.email,'member' AS role FROM device_shares s JOIN users u ON u.id=s.user_id WHERE s.device_id=? ORDER BY role DESC,email");
    $stmt->execute([$deviceId,$deviceId]);
    return $stmt->fetchAll();
}

function validate_settings(mixed $value): array {
    if(!is_array($value)) error_response('Некорректные настройки');
    $allowed=['enabled','intervals','controlled_users','show_timer','break_enabled','break_duration_minutes','work_duration_minutes'];
    $out=array_intersect_key($value,array_flip($allowed));
    foreach(['enabled','show_timer','break_enabled'] as $key) if(!isset($out[$key])||!is_bool($out[$key])) error_response("Некорректное поле $key");
    if(!isset($out['controlled_users'])||!is_array($out['controlled_users'])||count($out['controlled_users'])>32) error_response('Некорректные пользователи');
    $out['controlled_users']=array_values(array_unique(array_map(fn($v)=>text_limit(trim((string)$v),128),$out['controlled_users'])));
    foreach(['break_duration_minutes'=>180,'work_duration_minutes'=>1440] as $key=>$max){$out[$key]=filter_var($out[$key]??null,FILTER_VALIDATE_INT,['options'=>['min_range'=>1,'max_range'=>$max]]); if($out[$key]===false) error_response('Некорректные параметры перерывов');}
    if(!isset($out['intervals'])||!is_array($out['intervals'])||count($out['intervals'])>100) error_response('Некорректные интервалы');
    foreach($out['intervals'] as &$interval){
        if(!is_array($interval)||!preg_match('/^(?:[01]\d|2[0-3]):[0-5]\d$/',$interval['start']??'')||!preg_match('/^(?:[01]\d|2[0-3]):[0-5]\d$/',$interval['end']??'')||($interval['start']??'')===($interval['end']??'')) error_response('Некорректный интервал');
        $days=array_values(array_unique(array_map('intval',$interval['days']??[]))); if(!$days||array_diff($days,range(0,6))) error_response('Некорректные дни');
        $interval=['start'=>$interval['start'],'end'=>$interval['end'],'days'=>$days];
    }
    return $out;
}
function validate_user_statuses(mixed $value,array $available): array {
    if(!is_array($value)||count($value)>64) error_response('Некорректные статусы пользователей');
    $allowedNames=array_flip($available); $out=[];
    foreach($value as $row){
        if(!is_array($row)) error_response('Некорректный статус пользователя');
        $name=text_limit(trim((string)($row['name']??'')),128);
        $state=(string)($row['state']??''); $event=$row['next_event']??null; $seconds=$row['seconds']??null;
        if(!$name||!isset($allowedNames[$name])||!in_array($state,['disabled','uncontrolled','allowed','blocked','break'],true)) error_response('Некорректный статус пользователя');
        if($event!==null&&!in_array($event,['lock','unlock'],true)) error_response('Некорректное следующее событие');
        if($seconds!==null){$seconds=filter_var($seconds,FILTER_VALIDATE_INT,['options'=>['min_range'=>0,'max_range'=>691200]]);if($seconds===false)error_response('Некорректное время статуса');}
        $out[]=['name'=>$name,'controlled'=>(bool)($row['controlled']??false),'state'=>$state,'seconds'=>$seconds,'next_event'=>$event];
    }
    return $out;
}
function audit(?int $user,?string $device,string $action): void { db()->prepare('INSERT INTO audit_log(user_id,device_id,action,ip_hash,created_at) VALUES(?,?,?,?,?)')->execute([$user,$device,$action,client_ip_hash(),time()]); }

function send_verification_mail(string $email, string $url): bool {
    if ((cfg()['mail_transport'] ?? 'mail') === 'log') {
        return file_put_contents((string)cfg()['mail_log'], $email . "\t" . $url . "\n", FILE_APPEND | LOCK_EX) !== false;
    }
    $subject='=?UTF-8?B?'.base64_encode('Подтверждение регистрации TimeScreen').'?=';
    $body="Подтвердите регистрацию TimeScreen:\n$url\n\nСсылка действует 24 часа.";
    $from=(string)cfg()['mail_from'];
    $headers=implode("\r\n",['From: '.$from,'MIME-Version: 1.0','Content-Type: text/plain; charset=UTF-8','Content-Transfer-Encoding: 8bit']);
    $envelope=preg_match('/<([^<>\r\n]+)>/',$from,$matches)?$matches[1]:$from;
    if(!filter_var($envelope,FILTER_VALIDATE_EMAIL)) return false;
    return mail($email,$subject,$body,$headers,'-f'.$envelope);
}

function send_share_mail(string $email,string $deviceName,string $ownerEmail): bool {
    if ((cfg()['mail_transport'] ?? 'mail') === 'log') {
        return file_put_contents((string)cfg()['mail_log'], $email."\tDEVICE-SHARE\t".$deviceName."\n", FILE_APPEND | LOCK_EX) !== false;
    }
    $subject='=?UTF-8?B?'.base64_encode('Вам открыт доступ к TimeScreen').'?=';
    $url=(string)cfg()['base_url'];
    $body="Пользователь $ownerEmail открыл вам доступ к компьютеру «$deviceName» в TimeScreen.\n\nОткройте кабинет: $url\n";
    $from=(string)cfg()['mail_from'];
    $headers=implode("\r\n",['From: '.$from,'MIME-Version: 1.0','Content-Type: text/plain; charset=UTF-8','Content-Transfer-Encoding: 8bit']);
    $envelope=preg_match('/<([^<>\r\n]+)>/',$from,$matches)?$matches[1]:$from;
    return filter_var($envelope,FILTER_VALIDATE_EMAIL) ? mail($email,$subject,$body,$headers,'-f'.$envelope) : false;
}
