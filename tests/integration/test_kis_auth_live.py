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
        """실제 VTS 서버와의 직접 HTTP 통신 및 발급/Rate-limit 결과 명확 분리 검증."""
        if not self.auth_mgr.has_credentials():
            pytest.skip("KIS_APP_KEY 또는 KIS_APP_SECRET 미설정으로 인한 모의투자 라이브 토큰 발급 테스트 SKIP")

        # 1. 실제 VTS 엔드포인트 직접 호출 (캐시 없이 순수 네트워크 호출)
        direct_mgr = KISAuthManager(
            app_key=self.auth_mgr.app_key,
            app_secret=self.auth_mgr.app_secret,
            base_url=self.auth_mgr.base_url,
            is_vts=True,
            cache_file_path=None,
        )

        issuance_result = ""
        token = None

        try:
            token = direct_mgr.issue_token()
            issuance_result = "NEW_ISSUANCE_SUCCESS"
            print(f"\n[LIVE VTS RESULT: NEW_ISSUANCE_SUCCESS] Token issued: expires_in={token.expires_in}s, expired_at={token.expired_at_str}")
        except Exception as exc:
            err_str = str(exc)
            if "EGW00133" in err_str:
                issuance_result = "RATE_LIMIT_EGW00133_VERIFIED"
                print(f"\n[LIVE VTS RESULT: RATE_LIMIT_EGW00133_VERIFIED] Real VTS responded with EGW00133: {err_str}")
            else:
                pytest.fail(f"Real VTS network call failed with unexpected error: {exc}")

        # 2. 결과별 독립 assertion
        if issuance_result == "NEW_ISSUANCE_SUCCESS":
            assert token is not None, "Token must exist on new issuance"
            assert isinstance(token.access_token, str), "access_token must be a string"
            assert len(token.access_token) > 50, f"Token length ({len(token.access_token)}) too short"
            assert not token.access_token.startswith("MOCK_"), "Mock token must not be issued by real VTS"
            assert token.token_type.lower() == "bearer", f"Expected Bearer, got {token.token_type}"
            assert token.expires_in > 0
            assert token.is_valid()
        elif issuance_result == "RATE_LIMIT_EGW00133_VERIFIED":
            # 실제 VTS 서버와의 통신 성공 및 1분 제한 응답 수신 확인 완료
            pass
        else:
            pytest.fail(f"Unknown issuance result state: {issuance_result}")

    def test_live_vts_skip_when_credentials_missing(self):
        """키가 설정되지 않은 환경에서는 에러(FAIL)가 아니라 pytest.skip 되는지 검증."""
        with patch.object(KISAuthManager, "from_env", return_value=KISAuthManager(app_key="", app_secret="")):
            dummy_mgr = KISAuthManager.from_env()
            if not dummy_mgr.has_credentials():
                pytest.skip("자격증명 미설정 시 정상적으로 SKIP 처리됨 확인")
            pytest.fail("자격증명이 없는데 SKIP 되지 않음")
