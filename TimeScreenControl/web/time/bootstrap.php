<?php
declare(strict_types=1);

const SESSION_COOKIE = 'timescreen_session';

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
 last_seen_at INTEGER, created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_devices_pairing ON devices(pairing_hash, pairing_expires);
CREATE INDEX IF NOT EXISTS idx_devices_owner ON devices(owner_user_id);
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
SQL);
    $db->prepare('DELETE FROM sessions WHERE expires_at < ?')->execute([time()]);
    $db->prepare('DELETE FROM users WHERE verified_at IS NULL AND verify_expires < ?')->execute([time()]);
    $db->prepare('DELETE FROM devices WHERE owner_user_id IS NULL AND created_at < ?')->execute([time()-604800]);
}

function json_input(): array {
    $data = json_decode(file_get_contents('php://input') ?: '{}', true);
    if (!is_array($data)) error_response('Некорректный JSON', 400);
    return $data;
}

function json_response(array $data, int $status = 200): never {
    http_response_code($status); header('Content-Type: application/json; charset=utf-8'); header('Cache-Control: no-store');
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES); exit;
}
function error_response(string $message, int $status = 400): never { json_response(['ok'=>false,'error'=>$message], $status); }
function random_token(int $bytes = 32): string { return rtrim(strtr(base64_encode(random_bytes($bytes)), '+/', '-_'), '='); }
function token_hash(string $value): string { return hash_hmac('sha256', $value, cfg()['app_key']); }
function client_ip_hash(): string { return token_hash($_SERVER['REMOTE_ADDR'] ?? 'unknown'); }
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
    $db=db(); $now=time(); $start=$now-($now%$window); $identity=token_hash($identity); $db->beginTransaction();
    $stmt=$db->prepare('SELECT window_start,attempts FROM rate_limits WHERE bucket=? AND identity=?'); $stmt->execute([$bucket,$identity]); $row=$stmt->fetch();
    $attempts=($row && (int)$row['window_start']===$start)?(int)$row['attempts']+1:1;
    $db->prepare('INSERT INTO rate_limits(bucket,identity,window_start,attempts) VALUES(?,?,?,?) ON CONFLICT(bucket,identity) DO UPDATE SET window_start=excluded.window_start,attempts=excluded.attempts')->execute([$bucket,$identity,$start,$attempts]);
    $db->commit(); if($attempts>$max) error_response('Слишком много попыток. Повторите позже.',429);
}

function bearer(): string {
    $header=$_SERVER['HTTP_AUTHORIZATION']??'';
    if(!preg_match('/^Bearer\s+(.+)$/i',$header,$m)) error_response('Требуется авторизация устройства',401);
    return trim($m[1]);
}
function device_auth(): array {
    $parts=explode('.',bearer(),2);
    if(count($parts)!==2 || !preg_match('/^[a-f0-9-]{36}$/',$parts[0])) error_response('Недействительный токен устройства',401);
    $stmt=db()->prepare('SELECT * FROM devices WHERE id=?'); $stmt->execute([$parts[0]]); $row=$stmt->fetch();
    if(!$row || !hash_equals($row['token_hash'],token_hash($parts[1]))) error_response('Недействительный токен устройства',401);
    return $row;
}

function current_user(bool $csrf=false): array {
    $token=$_COOKIE[SESSION_COOKIE]??''; if(!$token) error_response('Требуется вход',401);
    $stmt=db()->prepare('SELECT u.*,s.csrf_hash FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?');
    $stmt->execute([token_hash($token),time()]); $user=$stmt->fetch(); if(!$user) error_response('Сессия истекла',401);
    if($csrf){$value=$_SERVER['HTTP_X_CSRF_TOKEN']??''; if(!$value || !hash_equals($user['csrf_hash'],token_hash($value))) error_response('Недействительный CSRF-токен',403);}
    return $user;
}
function set_session_cookie(string $token): void { setcookie(SESSION_COOKIE,$token,['expires'=>time()+2592000,'path'=>'/','secure'=>true,'httponly'=>true,'samesite'=>'Strict']); }

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
function audit(?int $user,?string $device,string $action): void { db()->prepare('INSERT INTO audit_log(user_id,device_id,action,ip_hash,created_at) VALUES(?,?,?,?,?)')->execute([$user,$device,$action,client_ip_hash(),time()]); }

function send_verification_mail(string $email, string $url): bool {
    if ((cfg()['mail_transport'] ?? 'mail') === 'log') {
        return file_put_contents((string)cfg()['mail_log'], $email . "\t" . $url . "\n", FILE_APPEND | LOCK_EX) !== false;
    }
    $subject='Подтверждение регистрации TimeScreen';
    $body="Подтвердите регистрацию TimeScreen:\n$url\n\nСсылка действует 24 часа.";
    return mail($email,$subject,$body,implode("\r\n",['From: '.cfg()['mail_from'],'Content-Type: text/plain; charset=UTF-8']));
}
