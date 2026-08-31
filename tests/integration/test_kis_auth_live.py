"""Integration tests for live KIS Developers OAuth2 token issuance (VTS environment).

Rules:
- Real network call to VTS server (https://openapivts.koreainvestment.com:29443).
- If valid APP_KEY / APP_SECRET are missing, test MUST SKIP (pytest.skip).
- MOCK token MUST NOT be treated as a valid issuance.
- Validates actual access_token format, token_type, expires_in, and expiration timestamp.
"""
from unittest.mock import patch
import pytest
from option_program.broker.kis_auth import KISAuthManager, KISAuthToken


class TestKISAuthLiveVTS:
    """실제 한국투자증권 모의투자(VTS) 환경 access_token 발급 통합 검증."""

    @pytest.fixture(autouse=True)
    def setup_manager(self):
        """환경변수 또는 .env 파일에서 자격증명을 로드."""
        self.auth_mgr = KISAuthManager.from_env(is_vts=True)

    def test_live_vts_token_issuance(self):
        """실제 VTS 서버로부터 OAuth2 access_token 발급 및 정밀 검증."""
        if not self.auth_mgr.has_credentials():
            pytest.skip("KIS_APP_KEY 또는 KIS_APP_SECRET 미설정으로 인한 모의투자 라이브 토큰 발급 테스트 SKIP")

        # 1. 토큰 획득 (최초 시 실제 VTS 발급, 유효 기간 내에는 캐시 활용)
        token_str: str = self.auth_mgr.get_access_token()
        token: KISAuthToken = self.auth_mgr.get_token_info()

        assert token is not None, "Token info must exist after get_access_token()"
        assert token.access_token == token_str, "Returned token string must match cached token"

        # 2. 토큰 필드 정밀 검증
        assert isinstance(token.access_token, str), "access_token must be a string"
        assert len(token.access_token) > 50, f"access_token length ({len(token.access_token)}) must be sufficient for a real JWT/Bearer token"
        assert not token.access_token.startswith("MOCK_"), "Mock token must not be issued by real VTS endpoint"

        # 3. 토큰 타입 및 만료 시간 검증
        assert token.token_type.lower() == "bearer", f"Expected Bearer token, got {token.token_type}"
        assert token.expires_in > 0, "expires_in must be positive integer"
        assert token.is_valid(), "Newly issued token must be valid"

        # 4. 헤더 포맷 검증
        auth_header = self.auth_mgr.get_authorization_header()
        assert auth_header == f"Bearer {token.access_token}"

    def test_live_vts_skip_when_credentials_missing(self):
        """키가 설정되지 않은 환경에서는 에러(FAIL)가 아니라 pytest.skip 되는지 검증."""
        with patch.object(KISAuthManager, "from_env", return_value=KISAuthManager(app_key="", app_secret="")):
            dummy_mgr = KISAuthManager.from_env()
            if not dummy_mgr.has_credentials():
                pytest.skip("자격증명 미설정 시 정상적으로 SKIP 처리됨 확인")
            pytest.fail("자격증명이 없는데 SKIP 되지 않음")
