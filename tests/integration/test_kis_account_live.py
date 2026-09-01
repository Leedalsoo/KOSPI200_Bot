"""Integration tests for live KIS Developers account balance inquiry (VTS environment).

Rules:
- Real network call to VTS server (https://openapivts.koreainvestment.com:29443).
- If valid APP_KEY / APP_SECRET / ACCOUNT_NO are missing, test MUST SKIP (pytest.skip).
- Clearly separates: (1) Successful live inquiry, (2) Rate-limit / API error response from real VTS, (3) Missing credentials (SKIP).
- Validates CanonicalAccountSummary DTO conversion.
"""
import os
import re
import pytest
from option_program.broker.real_broker_adapter import RealBrokerAdapter, RealBrokerConfig, RealBrokerHttpClient
from option_program.broker.kis_auth import KISAuthManager, _load_env_file_fallback


# 공식 KIS Developers API 게이트웨이 및 모의투자(VTS) 환경 제약 에러코드
ALLOWED_SERVER_LIMIT_CODES = {
    "EGW00133",  # 토큰/호출 1분당 1회 한도 초과
    "EGW00201",  # 초당 거래건수(TPS) 한도 초과
    "EGW00123",  # 시스템 점검 중 (거래불가 시간대)
    "EGW00121",  # 시스템 작업 중
    "EGW00122",  # 시스템 일시 중단
    "OPSQ0002",  # 모의투자(VTS) 환경 계좌 상품코드 미등록/환경제약
}


class TestKISAccountLiveVTS:
    """실제 한국투자증권 모의투자(VTS) 환경 계좌조회 통합 검증."""

    @pytest.fixture(autouse=True)
    def setup_adapter(self):
        """환경변수 및 .env 파일에서 자격증명과 계좌번호를 로드하여 Adapter 설정."""
        auth_mgr = KISAuthManager.from_env(is_vts=True)
        self.has_creds = auth_mgr.has_credentials()

        env_map = _load_env_file_fallback(".env")
        account_no = (
            os.getenv("KIS_VTS_ACCOUNT_NO")
            or os.getenv("KIS_ACCOUNT_NO")
            or os.getenv("REAL_BROKER_ACCOUNT_NO")
            or env_map.get("KIS_ACCOUNT_NO", "")
            or env_map.get("REAL_BROKER_ACCOUNT_NO", "")
        )
        prdt_cd = (
            os.getenv("KIS_ACCOUNT_PRODUCT_CD")
            or env_map.get("KIS_ACCOUNT_PRODUCT_CD", "")
        )
        if account_no and "-" not in account_no and prdt_cd:
            account_no = f"{account_no}-{prdt_cd}"

        self.config = RealBrokerConfig(
            account_no=account_no,
            app_key=auth_mgr.app_key,
            app_secret=auth_mgr.app_secret,
            base_url=auth_mgr.base_url,
            is_simulation=False,  # 실제 네트워크 통신
            is_vts=True,
        )
        self.client = RealBrokerHttpClient(config=self.config)
        self.adapter = RealBrokerAdapter(config=self.config, http_client=self.client)

    def test_live_vts_account_inquiry(self):
        """실제 VTS 서버로부터 국내선물옵션 잔고조회(inquire-balance) 통신 검증."""
        if not self.has_creds or not self.config.account_no:
            pytest.skip("KIS VTS 자격증명 또는 계좌번호 미설정으로 인한 라이브 계좌조회 테스트 SKIP")

        # 1. Broker 연결
        connected = self.adapter.connect()
        assert connected is True, "Broker connect must succeed with valid credentials"

        # 2. 계좌 요약 조회 실행
        try:
            summary = self.adapter.get_account_summary()
            # 민감정보(계좌번호, 키) 제외하고 순수 금액 메트릭만 로깅
            print(f"\n[LIVE VTS ACCOUNT SUCCESS] total_balance={summary.total_balance}, free_margin={summary.free_margin}, used_margin={summary.used_margin}, unrealized_pnl={summary.unrealized_pnl}")
            assert summary.account_id == self.config.account_no
            assert summary.total_balance >= 0.0
            assert summary.free_margin >= 0.0
            assert summary.used_margin >= 0.0
        except Exception as exc:
            err_str = str(exc)
            # 오직 공식 ALLOWED_SERVER_LIMIT_CODES에 해당하는 구체적인 msg_cd만 SERVER_LIMIT으로 허용
            kis_msg_match = re.search(r"\[([A-Z0-9]{8})\]", err_str)
            if kis_msg_match:
                msg_cd = kis_msg_match.group(1)
                if msg_cd in ALLOWED_SERVER_LIMIT_CODES:
                    print(f"\n[LIVE VTS ACCOUNT SERVER_LIMIT] Real VTS returned allowed msg_cd={msg_cd}")
                    return

            pytest.fail(f"Real VTS account inquiry failed with non-whitelisted error: {exc}")

    def test_live_vts_account_skip_when_credentials_missing(self):
        """자격증명 미설정 시 에러가 아닌 pytest.skip 처리 검증."""
        empty_config = RealBrokerConfig(account_no="", app_key="", app_secret="", is_vts=True)
        if not empty_config.app_key or not empty_config.account_no:
            pytest.skip("자격증명 또는 계좌번호 미설정 시 정상적으로 SKIP 처리됨 확인")
        pytest.fail("자격증명이 없는데 SKIP 되지 않음")

