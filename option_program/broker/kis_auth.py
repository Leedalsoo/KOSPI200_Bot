"""한국투자증권(KIS Developers) Open API OAuth2 인증 모듈.

모의투자(VTS) 및 실전투자 환경의 access_token 발급, 캐싱, 만료 관리 및 세션 헤더 제공.
- API 규격: POST /oauth2/tokenP
- 외부 서드파티 라이브러리 없이 Python 표준 라이브러리(urllib, json, time, os) 기반 구현.
- 키/시크릿 하드코딩 금지 (환경변수 또는 .env 로더 연동).
- KIS API 1분당 1회 토큰 발급 제한(EGW00133)에 대응하기 위해 로컬 파일/메모리 캐싱 지원.
"""
import os
import time
import orjson as json
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime

logger = logging.getLogger(__name__)

# KIS Developers 공식 엔드포인트 URL
KIS_VTS_BASE_URL: str = "https://openapivts.koreainvestment.com:29443"
KIS_REAL_BASE_URL: str = "https://openapi.koreainvestment.com:9443"
KIS_TOKEN_PATH: str = "/oauth2/tokenP"


class KISAuthError(Exception):
    """KIS OAuth2 인증 처리 중 발생하는 예외"""
    def __init__(self, message: str, error_code: Optional[str] = None, response_data: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.error_code = error_code
        self.response_data = response_data or {}


@dataclass
class KISAuthToken:
    """KIS OAuth2 발급 토큰 정보 DTO"""
    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 86400
    token_expired_at: float = 0.0
    expired_at_str: Optional[str] = None
    issued_at: float = field(default_factory=time.time)

    def is_valid(self, buffer_seconds: int = 60) -> bool:
        """토큰이 유효한지 검사 (만료 전 안전 마진 포함)."""
        if not self.access_token or not self.access_token.strip():
            return False
        # MOCK 토큰은 실제 유효 토큰으로 판정하지 않음
        if self.access_token.startswith("MOCK_"):
            return False
        now = time.time()
        return now < (self.token_expired_at - buffer_seconds)

    @classmethod
    def from_response(cls, data: Dict[str, Any], issued_at: Optional[float] = None) -> "KISAuthToken":
        """KIS 토큰 발급 API 응답 JSON에서 객체 생성."""
        access_token = data.get("access_token", "")
        token_type = data.get("token_type", "Bearer")
        expires_in = int(data.get("expires_in", 86400))
        expired_at_str = data.get("access_token_token_expired")

        now = issued_at if issued_at is not None else time.time()
        
        # 만료 시각 계산 (KIS 날짜 형식: "YYYY-MM-DD HH:MM:SS", KST UTC+9 기준)
        if expired_at_str:
            try:
                from datetime import timezone, timedelta
                kst = timezone(timedelta(hours=9))
                dt = datetime.strptime(expired_at_str.strip(), "%Y-%m-%d %H:%M:%S")
                token_expired_at = dt.replace(tzinfo=kst).timestamp()
            except Exception:
                token_expired_at = now + expires_in
        else:
            token_expired_at = now + expires_in

        return cls(
            access_token=access_token,
            token_type=token_type,
            expires_in=expires_in,
            token_expired_at=token_expired_at,
            expired_at_str=expired_at_str,
            issued_at=now
        )


def _load_env_file_fallback(env_path: str = ".env") -> Dict[str, str]:
    """외부 dotenv 패키지 없이 순수 파이썬으로 .env 파일 파싱 (Fallback용)."""
    env_vars: Dict[str, str] = {}
    if not os.path.exists(env_path):
        return env_vars
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                # 따옴표 제거
                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                env_vars[k] = v
    except Exception as e:
        logger.warning(f"[KISAuth] Failed to read .env file at {env_path}: {e}")
    return env_vars


class KISAuthManager:
    """한국투자증권 OAuth2 인증 관리자.
    
    토큰 발급(POST /oauth2/tokenP), 캐싱, 자동 갱신 및 공통 인증 헤더 구성을 전담.
    """
    def __init__(
        self,
        app_key: str = "",
        app_secret: str = "",
        base_url: str = KIS_VTS_BASE_URL,
        is_vts: bool = True,
        timeout: float = 10.0,
        cache_file_path: Optional[str] = None
    ):
        self.app_key = app_key.strip()
        self.app_secret = app_secret.strip()
        self.base_url = base_url.rstrip("/")
        self.is_vts = is_vts
        self.timeout = timeout
        self.cache_file_path = cache_file_path
        self._current_token: Optional[KISAuthToken] = None

        # 캐시 파일이 지정되어 있으면 기발급된 토큰 로드 시도
        if self.cache_file_path:
            self._load_token_from_cache()

    @classmethod
    def from_env(
        cls,
        is_vts: bool = True,
        env_file: Optional[str] = None,
        base_url: Optional[str] = None,
        cache_file_path: Optional[str] = None
    ) -> "KISAuthManager":
        """환경변수 및 .env 파일로부터 인증 정보를 로드하여 인스턴스를 생성."""
        # 1. 로컬 .env 파일 파싱 (환경변수에 없는 경우 보완)
        fallback_env = _load_env_file_fallback(env_file or ".env")

        def get_val(key: str, default: str = "") -> str:
            return os.getenv(key) or fallback_env.get(key, default)

        # 환경변수 조회 (모의/실전 및 일반 키 매핑 지원)
        app_key = (
            get_val("KIS_VTS_APP_KEY") if is_vts else get_val("KIS_REAL_APP_KEY")
        ) or get_val("KIS_APP_KEY") or get_val("REAL_BROKER_APP_KEY")

        app_secret = (
            get_val("KIS_VTS_APP_SECRET") if is_vts else get_val("KIS_REAL_APP_SECRET")
        ) or get_val("KIS_APP_SECRET") or get_val("REAL_BROKER_APP_SECRET")

        if base_url:
            resolved_base_url = base_url
        else:
            env_base_url = get_val("KIS_BASE_URL")
            if env_base_url:
                resolved_base_url = env_base_url
            else:
                resolved_base_url = KIS_VTS_BASE_URL if is_vts else KIS_REAL_BASE_URL

        # 기본 캐시 파일 경로 (data/ 디렉터리 활용)
        if cache_file_path is None:
            prefix = "vts" if is_vts else "real"
            cache_file_path = os.path.join("data", f".kis_token_cache_{prefix}.json")

        return cls(
            app_key=app_key,
            app_secret=app_secret,
            base_url=resolved_base_url,
            is_vts=is_vts,
            cache_file_path=cache_file_path
        )

    def _load_token_from_cache(self) -> None:
        """로컬 파일 캐시에서 토큰 로드."""
        if not self.cache_file_path or not os.path.exists(self.cache_file_path):
            return
        try:
            with open(self.cache_file_path, "rb") as f:
                data = json.loads(f.read())
                token = KISAuthToken(**data)
                if token.is_valid():
                    self._current_token = token
                    logger.info(f"[KISAuth] Loaded valid token from cache ({self.cache_file_path})")
        except Exception as e:
            logger.warning(f"[KISAuth] Failed to load cached token from {self.cache_file_path}: {e}")

    def _save_token_to_cache(self, token: KISAuthToken) -> None:
        """토큰을 로컬 파일 캐시에 저장."""
        if not self.cache_file_path:
            return
        try:
            cache_dir = os.path.dirname(self.cache_file_path)
            if cache_dir and not os.path.exists(cache_dir):
                os.makedirs(cache_dir, exist_ok=True)
            with open(self.cache_file_path, "wb") as f:
                f.write(json.dumps(asdict(token), option=json.OPT_INDENT_2))
        except Exception as e:
            logger.warning(f"[KISAuth] Failed to save token to cache {self.cache_file_path}: {e}")

    def has_credentials(self) -> bool:
        """인증에 필요한 App Key와 App Secret이 존재하는지 확인."""
        return bool(self.app_key and self.app_secret)

    def issue_token(self) -> KISAuthToken:
        """KIS OAuth2 토큰 발급 API를 호출하여 새 access_token을 발급받음.
        
        Raises:
            KISAuthError: 자격증명 부재, 네트워크 실패, 또는 KIS API 오류 응답 시 발생.
        """
        if not self.has_credentials():
            raise KISAuthError("KIS AppKey or AppSecret is missing. Cannot issue OAuth2 token.")

        endpoint = f"{self.base_url}{KIS_TOKEN_PATH}"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        data_bytes = json.dumps(payload)
        headers = {
            "Content-Type": "application/json; charset=UTF-8"
        }

        req = urllib.request.Request(endpoint, data=data_bytes, headers=headers, method="POST")

        logger.info(f"[KISAuth] Requesting OAuth2 token from {endpoint} (is_vts={self.is_vts})...")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_bytes = resp.read()
                resp_json = json.loads(resp_bytes.decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = ""
            err_json = {}
            try:
                err_body = e.read().decode("utf-8")
                err_json = json.loads(err_body)
            except Exception:
                pass
            
            # 1분당 1회 제한(EGW00133) 발생 시, 기존 유효 캐시가 있으면 재사용
            if err_json.get("error_code") == "EGW00133" and self._current_token and self._current_token.is_valid():
                logger.warning("[KISAuth] Rate limit (EGW00133) hit on token issuance, reusing valid cached token.")
                return self._current_token

            err_msg = f"HTTP Error {e.code} ({e.reason}): {err_body}"
            logger.error(f"[KISAuth] Failed to issue token: {err_msg}")
            raise KISAuthError(
                message=err_msg,
                error_code=err_json.get("error_code") or str(e.code),
                response_data=err_json
            ) from e
        except urllib.error.URLError as e:
            err_msg = f"Network connection failed: {e.reason}"
            logger.error(f"[KISAuth] Network error: {err_msg}")
            raise KISAuthError(message=err_msg) from e
        except Exception as e:
            err_msg = f"Unexpected error during token issuance: {e}"
            logger.error(f"[KISAuth] Unexpected error: {err_msg}")
            raise KISAuthError(message=err_msg) from e

        # 응답 필드 검증
        if "access_token" not in resp_json or not resp_json["access_token"]:
            err_code = resp_json.get("error_code") or resp_json.get("msg_cd") or "UNKNOWN_ERR"
            err_desc = resp_json.get("error_description") or resp_json.get("msg1") or str(resp_json)
            err_msg = f"Token missing in response: [{err_code}] {err_desc}"
            logger.error(f"[KISAuth] {err_msg}")
            raise KISAuthError(message=err_msg, error_code=err_code, response_data=resp_json)

        token = KISAuthToken.from_response(resp_json)
        self._current_token = token
        self._save_token_to_cache(token)
        logger.info(
            f"[KISAuth] Successfully issued OAuth2 access_token (expires_in={token.expires_in}s, "
            f"expired_at={token.expired_at_str or token.token_expired_at})"
        )
        return token

    def get_access_token(self, force_refresh: bool = False) -> str:
        """유효한 access_token 반환 (만료되었거나 force_refresh 시 자동 재발급)."""
        if force_refresh or self._current_token is None or not self._current_token.is_valid():
            self.issue_token()
        if self._current_token is None:
            raise KISAuthError("Failed to obtain a valid access token.")
        return self._current_token.access_token

    def get_token_info(self) -> Optional[KISAuthToken]:
        """현재 캐싱된 토큰 정보 반환."""
        return self._current_token

    def get_authorization_header(self, force_refresh: bool = False) -> str:
        """Bearer 헤더 문자열 반환."""
        token = self.get_access_token(force_refresh=force_refresh)
        token_type = self._current_token.token_type if self._current_token else "Bearer"
        return f"{token_type} {token}"

    def get_auth_headers(self, tr_id: str = "", force_refresh: bool = False) -> Dict[str, str]:
        """KIS API 요청용 표준 인증 헤더 딕셔너리 구성."""
        auth_header = self.get_authorization_header(force_refresh=force_refresh)
        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "authorization": auth_header,
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        if tr_id:
            headers["tr_id"] = tr_id
        return headers
