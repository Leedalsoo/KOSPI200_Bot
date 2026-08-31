"""Unit tests for option_program.broker.kis_auth module.

Tests cover:
- KISAuthToken validation & lifecycle
- KISAuthManager credential loading & priority
- HTTP request / response mock handling (success, HTTP errors, network errors, API errors)
- Token caching and forced refresh behavior
- Header formatting
"""
import io
import time
import urllib.error
import urllib.request
from unittest.mock import patch, MagicMock

import orjson as json
import pytest

from option_program.broker.kis_auth import (
    KISAuthToken,
    KISAuthManager,
    KISAuthError,
    _load_env_file_fallback,
    KIS_VTS_BASE_URL,
    KIS_REAL_BASE_URL,
)


class TestKISAuthToken:
    def test_token_validity_lifecycle(self):
        now = time.time()
        # 유효한 토큰 (86400초 후 만료)
        token = KISAuthToken(
            access_token="valid_jwt_token_sample_12345",
            token_type="Bearer",
            expires_in=86400,
            token_expired_at=now + 86400,
            issued_at=now,
        )
        assert token.is_valid() is True
        assert token.is_valid(buffer_seconds=60) is True

        # 만료 임박 토큰 (만료 30초 전, buffer_seconds=60 이면 False)
        near_expiry_token = KISAuthToken(
            access_token="near_expiry_token_12345",
            token_type="Bearer",
            expires_in=30,
            token_expired_at=now + 30,
            issued_at=now,
        )
        assert near_expiry_token.is_valid(buffer_seconds=60) is False
        assert near_expiry_token.is_valid(buffer_seconds=10) is True

        # 이미 만료된 토큰
        expired_token = KISAuthToken(
            access_token="expired_token_12345",
            token_type="Bearer",
            expires_in=86400,
            token_expired_at=now - 10,
            issued_at=now - 86410,
        )
        assert expired_token.is_valid() is False

    def test_token_empty_or_mock_invalidation(self):
        now = time.time()
        # 빈 문자열 토큰
        empty_token = KISAuthToken(
            access_token="",
            token_expired_at=now + 86400,
        )
        assert empty_token.is_valid() is False

        # MOCK 토큰은 실제 발급으로 판정하지 않음
        mock_token = KISAuthToken(
            access_token="MOCK_BEARER_TOKEN_2026_PROD",
            token_expired_at=now + 86400,
        )
        assert mock_token.is_valid() is False

    def test_token_from_response_parsing(self):
        from datetime import datetime
        now = time.time()
        expired_str = datetime.fromtimestamp(now + 86400).strftime("%Y-%m-%d %H:%M:%S")
        resp_data = {
            "access_token": "actual_issued_access_token_jwt",
            "token_type": "Bearer",
            "expires_in": 86400,
            "access_token_token_expired": expired_str,
        }
        token = KISAuthToken.from_response(resp_data, issued_at=now)
        assert token.access_token == "actual_issued_access_token_jwt"
        assert token.token_type == "Bearer"
        assert token.expires_in == 86400
        assert token.expired_at_str == expired_str
        assert token.token_expired_at > now
        assert token.is_valid() is True


class TestKISAuthManager:
    def test_has_credentials(self):
        mgr_empty = KISAuthManager()
        assert mgr_empty.has_credentials() is False

        mgr_valid = KISAuthManager(app_key="TEST_KEY", app_secret="TEST_SECRET")
        assert mgr_valid.has_credentials() is True

    def test_issue_token_without_credentials_raises_error(self):
        mgr = KISAuthManager(app_key="", app_secret="")
        with pytest.raises(KISAuthError) as excinfo:
            mgr.issue_token()
        assert "missing" in str(excinfo.value)

    @patch("urllib.request.urlopen")
    def test_issue_token_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "access_token": "test_real_access_token_vts",
            "token_type": "Bearer",
            "expires_in": 86400,
            "access_token_token_expired": "2026-09-01 12:00:00",
        })
        mock_urlopen.return_value.__enter__.return_value = mock_response

        mgr = KISAuthManager(
            app_key="VTS_KEY_123",
            app_secret="VTS_SECRET_456",
            base_url=KIS_VTS_BASE_URL,
            is_vts=True,
        )

        token = mgr.issue_token()
        assert token.access_token == "test_real_access_token_vts"
        assert token.token_type == "Bearer"
        assert token.is_valid() is True
        assert mgr.get_token_info() is token

        # Header check
        headers = mgr.get_auth_headers(tr_id="TTTC8001R")
        assert headers["authorization"] == "Bearer test_real_access_token_vts"
        assert headers["appkey"] == "VTS_KEY_123"
        assert headers["appsecret"] == "VTS_SECRET_456"
        assert headers["tr_id"] == "TTTC8001R"

    @patch("urllib.request.urlopen")
    def test_token_caching_and_force_refresh(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "access_token": "cached_access_token_sample",
            "token_type": "Bearer",
            "expires_in": 86400,
        })
        mock_urlopen.return_value.__enter__.return_value = mock_response

        mgr = KISAuthManager(app_key="KEY", app_secret="SECRET")

        # 1st call -> issues token via HTTP
        t1 = mgr.get_access_token()
        assert t1 == "cached_access_token_sample"
        assert mock_urlopen.call_count == 1

        # 2nd call -> uses cached token (no additional HTTP request)
        t2 = mgr.get_access_token(force_refresh=False)
        assert t2 == "cached_access_token_sample"
        assert mock_urlopen.call_count == 1

        # 3rd call -> force_refresh=True triggers new HTTP request
        t3 = mgr.get_access_token(force_refresh=True)
        assert t3 == "cached_access_token_sample"
        assert mock_urlopen.call_count == 2

    @patch("urllib.request.urlopen")
    def test_issue_token_http_error(self, mock_urlopen):
        err_body = json.dumps({
            "error_code": "EGW00123",
            "error_description": "Invalid credentials",
        })
        http_error = urllib.error.HTTPError(
            url="https://openapivts.koreainvestment.com:29443/oauth2/tokenP",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=io.BytesIO(err_body),
        )
        mock_urlopen.side_effect = http_error

        mgr = KISAuthManager(app_key="BAD_KEY", app_secret="BAD_SECRET")
        with pytest.raises(KISAuthError) as excinfo:
            mgr.issue_token()
        assert "401" in str(excinfo.value)
        assert excinfo.value.error_code == "EGW00123"

    @patch("urllib.request.urlopen")
    def test_issue_token_missing_token_in_response(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "error_code": "ERR_AUTH",
            "error_description": "Failed to authenticate",
        })
        mock_urlopen.return_value.__enter__.return_value = mock_response

        mgr = KISAuthManager(app_key="KEY", app_secret="SECRET")
        with pytest.raises(KISAuthError) as excinfo:
            mgr.issue_token()
        assert "Token missing" in str(excinfo.value)
        assert excinfo.value.error_code == "ERR_AUTH"

    @patch("urllib.request.urlopen")
    def test_issue_token_url_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        mgr = KISAuthManager(app_key="KEY", app_secret="SECRET")
        with pytest.raises(KISAuthError) as excinfo:
            mgr.issue_token()
        assert "Network connection failed" in str(excinfo.value)


class TestKISAuthEnvironmentLoading:
    def test_load_env_file_fallback(self, tmp_path):
        env_file = tmp_path / ".env.test"
        env_file.write_text(
            "# Comment line\n"
            "KIS_APP_KEY=MY_TEST_KEY\n"
            "KIS_APP_SECRET='MY_TEST_SECRET'\n"
            "KIS_BASE_URL=\"https://custom.url:1234\"\n"
            "EMPTY_VAL=\n"
            "INVALID_LINE\n",
            encoding="utf-8",
        )
        loaded = _load_env_file_fallback(str(env_file))
        assert loaded["KIS_APP_KEY"] == "MY_TEST_KEY"
        assert loaded["KIS_APP_SECRET"] == "MY_TEST_SECRET"
        assert loaded["KIS_BASE_URL"] == "https://custom.url:1234"
        assert loaded["EMPTY_VAL"] == ""

    def test_from_env_priority(self, monkeypatch):
        # 1. Environment variables set
        monkeypatch.setenv("KIS_APP_KEY", "ENV_APP_KEY")
        monkeypatch.setenv("KIS_APP_SECRET", "ENV_APP_SECRET")
        monkeypatch.setenv("KIS_BASE_URL", "https://custom.base.url")

        mgr = KISAuthManager.from_env(is_vts=True, env_file="/non/existent/path")
        assert mgr.app_key == "ENV_APP_KEY"
        assert mgr.app_secret == "ENV_APP_SECRET"
        assert mgr.base_url == "https://custom.base.url"
        assert mgr.is_vts is True

    def test_from_env_default_urls(self, monkeypatch):
        monkeypatch.delenv("KIS_BASE_URL", raising=False)
        monkeypatch.delenv("KIS_APP_KEY", raising=False)
        monkeypatch.delenv("KIS_APP_SECRET", raising=False)

        mgr_vts = KISAuthManager.from_env(is_vts=True, env_file="/non/existent/path")
        assert mgr_vts.base_url == KIS_VTS_BASE_URL

        mgr_real = KISAuthManager.from_env(is_vts=False, env_file="/non/existent/path")
        assert mgr_real.base_url == KIS_REAL_BASE_URL
