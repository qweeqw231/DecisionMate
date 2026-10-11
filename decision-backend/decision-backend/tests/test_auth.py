# -*- coding: utf-8 -*-
"""
可选鉴权测试（P2-3）

默认关闭（DM_AUTH_TOKEN 未设置时行为与此前完全一致）；设置后
除 /api/health 与静态资源外的所有 /api/* 都要求携带令牌。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support  # noqa: F401

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

TOKEN = "s3cret-token-for-tests"


class AuthTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        self._orig = main._AUTH_TOKEN_CACHE
        self._set_token("")

    def tearDown(self):
        main._AUTH_TOKEN_CACHE = self._orig

    def _set_token(self, token: str):
        main._AUTH_TOKEN_CACHE = token


class TestAuthDisabled(AuthTestBase):
    def test_requests_pass_through_when_no_token_configured(self):
        self.assertEqual(self.client.get("/api/conversations").status_code, 200)

    def test_health_reports_auth_not_required(self):
        body = self.client.get("/api/health").json()
        self.assertFalse(body["auth_required"])

    def test_a_wrong_token_is_ignored_when_auth_is_off(self):
        resp = self.client.get("/api/conversations",
                               headers={"Authorization": "Bearer whatever"})
        self.assertEqual(resp.status_code, 200)


class TestAuthEnabled(AuthTestBase):
    def setUp(self):
        super().setUp()
        self._set_token(TOKEN)

    def test_missing_token_returns_401(self):
        resp = self.client.get("/api/conversations")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("令牌", resp.json()["detail"])

    def test_bearer_token_is_accepted(self):
        resp = self.client.get("/api/conversations",
                               headers={"Authorization": f"Bearer {TOKEN}"})
        self.assertEqual(resp.status_code, 200)

    def test_x_auth_token_header_is_accepted(self):
        resp = self.client.get("/api/conversations", headers={"X-Auth-Token": TOKEN})
        self.assertEqual(resp.status_code, 200)

    def test_wrong_token_returns_401(self):
        for value in ("wrong", TOKEN + "x", TOKEN[:-1], ""):
            with self.subTest(value=value):
                resp = self.client.get("/api/conversations",
                                       headers={"Authorization": f"Bearer {value}"})
                self.assertEqual(resp.status_code, 401)

    def test_bearer_prefix_is_case_insensitive(self):
        resp = self.client.get("/api/conversations",
                               headers={"Authorization": f"bearer {TOKEN}"})
        self.assertEqual(resp.status_code, 200)

    def test_health_stays_open_and_reports_requirement(self):
        """健康检查必须开放：前端要靠它区分「连不上」和「令牌不对」。"""
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["auth_required"])

    def test_static_frontend_is_not_blocked(self):
        """前端静态资源本身不含个人数据，不需要令牌即可加载。"""
        self.assertNotEqual(self.client.get("/").status_code, 401)
        self.assertNotEqual(self.client.get("/personas").status_code, 401)

    def test_unknown_api_path_still_requires_auth(self):
        """未知路径也要挡在鉴权之后，避免用 404/401 的差异探测路由。"""
        self.assertEqual(self.client.get("/api/definitely-not-a-route").status_code, 401)
        resp = self.client.get("/api/definitely-not-a-route",
                               headers={"Authorization": f"Bearer {TOKEN}"})
        self.assertEqual(resp.status_code, 404)

    def test_all_mutating_endpoints_are_protected(self):
        """逐个抽查写接口，确认鉴权覆盖完整（含删除类操作）。"""
        calls = [
            ("POST", "/api/conversations", {"title": "x"}),
            ("DELETE", "/api/conversations", None),
            ("POST", "/api/boundary-config", {"enabled": False}),
            ("GET", "/api/system-audit", None),
            ("GET", "/api/user-profile", None),
            ("GET", "/api/personas", None),
        ]
        for method, path, payload in calls:
            with self.subTest(path=path):
                resp = self.client.request(method, path, json=payload)
                self.assertEqual(resp.status_code, 401, f"{method} {path} 未被鉴权覆盖")

    def test_preflight_is_not_blocked(self):
        """CORS 预检不带自定义头，若被鉴权挡住会直接破坏跨机访问。"""
        resp = self.client.options("/api/conversations",
                                   headers={"Origin": "http://example.com",
                                            "Access-Control-Request-Method": "GET"})
        self.assertNotEqual(resp.status_code, 401)


class TestTokenSource(AuthTestBase):
    def test_empty_env_var_means_disabled(self):
        os.environ["DM_AUTH_TOKEN"] = ""
        main._AUTH_TOKEN_CACHE = None
        try:
            self.assertEqual(main.auth_token(), "")
        finally:
            os.environ.pop("DM_AUTH_TOKEN", None)

    def test_env_var_is_read_and_stripped(self):
        os.environ["DM_AUTH_TOKEN"] = f"  {TOKEN}  "
        main._AUTH_TOKEN_CACHE = None
        try:
            self.assertEqual(main.auth_token(), TOKEN)
        finally:
            os.environ.pop("DM_AUTH_TOKEN", None)


if __name__ == "__main__":
    unittest.main()
