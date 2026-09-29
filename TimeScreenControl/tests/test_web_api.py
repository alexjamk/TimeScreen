"""End-to-end API test using PHP's local development server."""

import json
import os
import shutil
import socket
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
        php_path = lambda p: str(p).replace("\\", "/").replace("'", "\\'")
        config.write_text(
            "<?php return ["
            f"'db_path'=>'{php_path(root / 'test.sqlite')}',"
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

    def call(self, action, payload=None, headers=None, cookie=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(self.base + "/api.php?action=" + action, data=data, method="GET" if payload is None else "POST", headers={"Content-Type":"application/json", **(headers or {})})
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
        verify_url = self.mail_log.read_text(encoding="utf-8").splitlines()[-1].split("\t",1)[1]
        with urllib.request.urlopen(verify_url, timeout=3) as response: self.assertIn("Email подтверждён", response.read().decode())
        logged, headers = self.call("login", {"email":email,"password":password}); csrf=logged["csrf"]
        cookie = headers.get("Set-Cookie").split(";",1)[0]
        restored,_ = self.call("me", None, cookie=cookie); csrf=restored["csrf"]
        device_id=str(uuid.uuid4()); token="t"*43; auth={"Authorization":f"Bearer {device_id}.{token}"}
        self.call("device-register", {"device_id":device_id,"token":token,"name":"Test PC","platform":"Windows"})
        self.call("device-pair-code", {"code":"123456"}, auth)
        paired,_=self.call("pair", {"code":"123456"}, {"X-CSRF-Token":csrf}, cookie); self.assertEqual(paired["device_id"],device_id)
        config={"enabled":True,"intervals":[{"start":"08:00","end":"21:00","days":[0,1,2,3,4]}],"controlled_users":["Child"],"show_timer":True,"break_enabled":True,"break_duration_minutes":10,"work_duration_minutes":60}
        synced,_=self.call("device-sync", {"known_revision":0,"local_dirty":True,"config":config,"available_users":["Child","Admin"]}, auth); self.assertEqual(synced["revision"],1)
        devices,_=self.call("devices", None, cookie=cookie); self.assertEqual(devices["devices"][0]["available_users"],["Child","Admin"])
        config["enabled"]=False
        self.call("device-config", {"device_id":device_id,"config":config}, {"X-CSRF-Token":csrf}, cookie)
        remote,_=self.call("device-sync", {"known_revision":1,"local_dirty":False,"config":dict(config,enabled=True),"available_users":["Child"]}, auth); self.assertFalse(remote["config"]["enabled"])
        self.call("grant-time", {"device_id":device_id,"minutes":30}, {"X-CSRF-Token":csrf}, cookie)
        command,_=self.call("device-sync", {"known_revision":remote["revision"],"local_dirty":False,"config":config,"available_users":["Child"]}, auth)
        self.assertEqual(command["commands"][0]["payload"]["minutes"],30)
        self.call("device-ack", {"command_ids":[command["commands"][0]["id"]]}, auth)
        self.call("unlink", {"device_id":device_id}, {"X-CSRF-Token":csrf}, cookie)
        revoked,_=self.call("device-revoke", {}, auth); self.assertTrue(revoked["ok"])


if __name__ == "__main__":
    unittest.main()
