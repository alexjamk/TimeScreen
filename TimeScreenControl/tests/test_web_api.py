"""End-to-end API test using PHP's local development server."""

import json
import os
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path


PHP = shutil.which("php")
WEB_ROOT = Path(__file__).parent.parent / "web" / "time"


@unittest.skipUnless(PHP, "PHP is not installed")
class TestWebApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        sock = socket.socket(); sock.bind(("127.0.0.1", 0)); cls.port = sock.getsockname()[1]; sock.close()
        cls.base = f"http://127.0.0.1:{cls.port}"
        config = root / "config.php"
        cls.db_path = root / "test.sqlite"
        php_path = lambda p: str(p).replace("\\", "/").replace("'", "\\'")
        config.write_text(
            "<?php return ["
            f"'db_path'=>'{php_path(cls.db_path)}',"
            "'app_key'=>'" + "ab" * 32 + "',"
            f"'base_url'=>'{cls.base}',"
            "'mail_from'=>'test@example.invalid','mail_transport'=>'log',"
            f"'mail_log'=>'{php_path(root / 'mail.log')}'"
            "];", encoding="utf-8",
        )
        cls.mail_log = root / "mail.log"
        env = dict(os.environ, TIMESCREEN_CONFIG=str(config))
        cls.server = subprocess.Popen([PHP, "-S", f"127.0.0.1:{cls.port}", "-t", str(WEB_ROOT)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            try:
                urllib.request.urlopen(cls.base + "/", timeout=.3).close(); break
            except Exception:
                time.sleep(.1)
        else:
            raise RuntimeError("PHP test server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate(); cls.server.wait(timeout=5); cls.temp.cleanup()

    def call(self, action, payload=None, headers=None, cookie=None, query=""):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(self.base + "/api.php?action=" + action + query, data=data, method="GET" if payload is None else "POST", headers={"Content-Type":"application/json", **(headers or {})})
        if cookie: request.add_header("Cookie", cookie)
        with urllib.request.urlopen(request, timeout=3) as response:
            return json.loads(response.read()), response.headers

    def test_registration_pairing_sync_and_grant(self):
        with self.assertRaises(urllib.error.HTTPError) as weak:
            self.call("register", {"email":f"weak-{uuid.uuid4()}@example.test","password":"six666"})
        self.assertEqual(weak.exception.code,400)
        weak.exception.close()
        email = f"parent-{uuid.uuid4()}@example.test"; password = "seven77"
        created, _ = self.call("register", {"email":email,"password":password}); self.assertTrue(created["ok"])
        resent, _ = self.call("resend-verification", {"email":email}); self.assertTrue(resent["ok"])
        verify_url = self.mail_log.read_text(encoding="utf-8").splitlines()[-1].split("\t",1)[1]
        with urllib.request.urlopen(verify_url, timeout=3) as response: self.assertIn("Email подтверждён", response.read().decode())
        logged, headers = self.call("login", {"email":email,"password":password}); csrf=logged["csrf"]
        cookie = headers.get("Set-Cookie").split(";",1)[0]
        restored,_ = self.call("me", None, cookie=cookie); csrf=restored["csrf"]
        device_id=str(uuid.uuid4()); token="t"*43; auth={"Authorization":f"Bearer {device_id}.{token}"}
        self.call("device-register", {"device_id":device_id,"token":token,"name":"Test PC","platform":"Windows"})
        for _ in range(25):
            self.call("device-register", {"device_id":device_id,"token":token,"name":"Test PC","platform":"Windows"})
        self.call("device-pair-code", {"code":"123456"}, auth)
        paired,_=self.call("pair", {"code":"123456"}, {"X-CSRF-Token":csrf}, cookie); self.assertEqual(paired["device_id"],device_id)
        config={"enabled":True,"intervals":[{"start":"08:00","end":"21:00","days":[0,1,2,3,4]}],"controlled_users":["Child"],"show_timer":True,"break_enabled":True,"break_duration_minutes":10,"work_duration_minutes":60}
        statuses=[{"name":"Child","controlled":True,"state":"allowed","seconds":3600,"next_event":"lock"},{"name":"Admin","controlled":False,"state":"uncontrolled","seconds":None,"next_event":None}]
        synced,_=self.call("device-sync", {"known_revision":0,"local_dirty":True,"config":config,"available_users":["Child","Admin"],"user_statuses":statuses}, auth); self.assertEqual(synced["revision"],1)
        devices,_=self.call("devices", None, cookie=cookie); self.assertEqual(devices["devices"][0]["available_users"],["Child","Admin"]); self.assertEqual(devices["devices"][0]["user_statuses"][0]["state"],"allowed")
        config["enabled"]=False
        self.call("device-config", {"device_id":device_id,"config":config}, {"X-CSRF-Token":csrf}, cookie)
        child_status=[{"name":"Child","controlled":True,"state":"blocked","seconds":600,"next_event":"unlock"}]
        remote,_=self.call("device-sync", {"known_revision":1,"local_dirty":False,"config":dict(config,enabled=True),"available_users":["Child"],"user_statuses":child_status}, auth); self.assertFalse(remote["config"]["enabled"])
        granted,_=self.call("grant-time", {"device_id":device_id,"username":"Child","minutes":30}, {"X-CSRF-Token":csrf}, cookie)
        pending,_=self.call("command-status", None, cookie=cookie, query=f"&id={granted['command_id']}")
        self.assertEqual(pending["status"], "pending")
        command,_=self.call("device-sync", {"known_revision":remote["revision"],"local_dirty":False,"config":config,"available_users":["Child"],"user_statuses":child_status}, auth)
        self.assertEqual(command["commands"][0]["payload"]["minutes"],30)
        self.assertEqual(command["commands"][0]["payload"]["username"],"Child")
        delivered,_=self.call("command-status", None, cookie=cookie, query=f"&id={granted['command_id']}")
        self.assertEqual(delivered["status"], "delivered")
        self.call("device-ack", {"command_ids":[command["commands"][0]["id"]]}, auth)
        done,_=self.call("command-status", None, cookie=cookie, query=f"&id={granted['command_id']}")
        self.assertEqual(done["status"], "done")

        member_email=f"member-{uuid.uuid4()}@example.test"; member_password="another7"
        self.call("register", {"email":member_email,"password":member_password})
        member_verify_url=self.mail_log.read_text(encoding="utf-8").splitlines()[-1].split("\t",1)[1]
        with urllib.request.urlopen(member_verify_url, timeout=3) as response: self.assertIn("Email подтверждён", response.read().decode())
        member_login,member_headers=self.call("login", {"email":member_email,"password":member_password})
        member_cookie=member_headers.get("Set-Cookie").split(";",1)[0]; member_csrf=member_login["csrf"]
        shared,_=self.call("device-share", {"device_id":device_id,"email":member_email}, {"X-CSRF-Token":csrf}, cookie)
        self.assertEqual(len(shared["members"]),2)
        member_devices,_=self.call("devices", None, cookie=member_cookie)
        self.assertEqual(member_devices["devices"][0]["access_role"],"member")
        self.assertEqual(len(member_devices["devices"][0]["members"]),2)
        shared_config=dict(config,enabled=True)
        self.call("device-config", {"device_id":device_id,"config":shared_config}, {"X-CSRF-Token":member_csrf}, member_cookie)
        member_grant,_=self.call("grant-time", {"device_id":device_id,"username":"Child","minutes":10}, {"X-CSRF-Token":member_csrf}, member_cookie)
        self.assertGreater(member_grant["command_id"],granted["command_id"])
        left,_=self.call("leave-device", {"device_id":device_id}, {"X-CSRF-Token":member_csrf}, member_cookie)
        self.assertTrue(left["ok"])
        member_devices,_=self.call("devices", None, cookie=member_cookie)
        self.assertEqual(member_devices["devices"],[])
        for index, code in enumerate(("234567", "345678"), start=2):
            extra_id=str(uuid.uuid4()); extra_token=(str(index)*43); extra_auth={"Authorization":f"Bearer {extra_id}.{extra_token}"}
            self.call("device-register", {"device_id":extra_id,"token":extra_token,"name":f"PC {index}","platform":"Windows"})
            self.call("device-pair-code", {"code":code}, extra_auth)
            self.call("pair", {"code":code}, {"X-CSRF-Token":csrf}, cookie)
        fourth_id=str(uuid.uuid4()); fourth_token="4"*43; fourth_auth={"Authorization":f"Bearer {fourth_id}.{fourth_token}"}
        self.call("device-register", {"device_id":fourth_id,"token":fourth_token,"name":"PC 4","platform":"Windows"})
        self.call("device-pair-code", {"code":"456789"}, fourth_auth)
        with self.assertRaises(urllib.error.HTTPError) as limit:
            self.call("pair", {"code":"456789"}, {"X-CSRF-Token":csrf}, cookie)
        self.assertEqual(limit.exception.code,409); limit.exception.close()
        self.call("unlink", {"device_id":device_id}, {"X-CSRF-Token":csrf}, cookie)
        revoked,_=self.call("device-revoke", {}, auth); self.assertTrue(revoked["ok"])

    def test_security_headers_body_limit_and_login_rate_limit(self):
        response = urllib.request.urlopen(self.base + "/api.php?action=health", timeout=3)
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("Cross-Origin-Opener-Policy"), "same-origin")
        self.assertIn("frame-ancestors 'none'", response.headers.get("Content-Security-Policy", ""))
        response.close()

        oversized = urllib.request.Request(
            self.base + "/api.php?action=login",
            data=json.dumps({"email":"large@example.test","password":"x" * 66000}).encode(),
            method="POST",
            headers={"Content-Type":"application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as rejected:
            urllib.request.urlopen(oversized, timeout=3)
        self.assertEqual(rejected.exception.code, 413)
        rejected.exception.close()

        for _ in range(10):
            with self.assertRaises(urllib.error.HTTPError) as invalid:
                self.call("login", {"email":"brute-force@example.test","password":"incorrect"})
            self.assertEqual(invalid.exception.code, 401)
            invalid.exception.close()
        with self.assertRaises(urllib.error.HTTPError) as limited:
            self.call("login", {"email":"brute-force@example.test","password":"incorrect"})
        self.assertEqual(limited.exception.code, 429)
        self.assertIsNotNone(limited.exception.headers.get("Retry-After"))
        limited.exception.close()

    def test_health_does_not_fail_when_maintenance_writer_is_busy(self):
        urllib.request.urlopen(self.base + "/api.php?action=health", timeout=3).close()
        connection = sqlite3.connect(self.db_path, timeout=1)
        try:
            connection.execute("UPDATE app_meta SET value='0' WHERE key='last_maintenance'")
            connection.commit()
            connection.execute("BEGIN IMMEDIATE")
            response = urllib.request.urlopen(self.base + "/api.php?action=health", timeout=3)
            self.assertEqual(json.loads(response.read())["ok"], True)
            response.close()
        finally:
            connection.rollback()
            connection.close()


if __name__ == "__main__":
    unittest.main()
