"""Typed application settings — the unified Tayf Studio configuration.

Every value comes from the environment (or the repo-root ``.env``).
No secret ever lives in source code. In production ``JWT_SECRET`` MUST be
provided; dev/test get an ephemeral one (tokens simply invalidate on restart).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ---
    APP_NAME: str = "tayf-backend"
    APP_ENV: str = "development"  # development | test | production
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    API_V1_PREFIX: str = "/api/v1"
    # Comma-separated browser origins allowed to call the API.
    CORS_ORIGINS: str = (
        "http://localhost:5173,http://localhost:3000,"
        "http://127.0.0.1:5173,http://127.0.0.1:3000"
    )

    # --- Database (SQLite by default: Termux-friendly, PostgreSQL-ready) ---
    DATABASE_URL: str = "sqlite:///./tayf.db"
    # Echo SQL only when explicitly asked (never in production).
    DB_ECHO: bool = False

    # --- Auth (Argon2id + JWT) ---
    JWT_SECRET: str = ""  # REQUIRED in production. Generate: python -c "import secrets; print(secrets.token_hex(32))"
    JWT_EXPIRES_MINUTES: int = 120
    JWT_REFRESH_EXPIRES_DAYS: int = 30

    # --- Rate limiting (in-memory sliding window, per client IP) ---
    RATELIMIT_ENABLED: bool = True
    RATELIMIT_WINDOW_SECONDS: int = 60
    RATELIMIT_AUTH_LIMIT: int = 10  # register/login/refresh attempts per window
    RATELIMIT_JOB_LIMIT: int = 30  # generation jobs created per window

    # --- Artifact URL signing (local storage) ---
    # false -> /files URLs require a short-lived HMAC signature (secure default)
    FILES_PUBLIC: bool = False

    # --- Observability ---
    METRICS_ENABLED: bool = True  # exposes GET /api/v1/metrics (aggregate counters)

    # --- AI providers ---
    # mock            -> offline, clearly-simulated output (tests / no keys)
    # zai_gateway     -> real LLM storyboard + real keyframes via ai-gateway sidecar
    # openai_compatible -> any OpenAI-compatible API (bring your own key)
    AI_PROVIDER: str = "mock"
    AI_GATEWAY_URL: str = "http://127.0.0.1:3030"
    AI_GATEWAY_TOKEN: str = ""
    AI_GATEWAY_TIMEOUT: int = 240
    OPENAI_BASE_URL: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_IMAGE_SIZE: str = "1344x768"

    # --- Storage ---
    # local -> files on disk (Termux default) | s3 -> any S3-compatible (MinIO etc.)
    STORAGE_BACKEND: str = "local"
    LOCAL_STORAGE_DIR: str = "./data/storage"
    S3_ENDPOINT: str = ""
    S3_BUCKET: str = ""
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_REGION: str = "us-east-1"
    STORAGE_TTL_DAYS: int = 7
    CLEANUP_INTERVAL_MINUTES: int = 60

    # --- Credits ---
    SIGNUP_CREDITS: int = 100
    CREDIT_PER_SCENE: int = 1

    # --- Content safety ---
    SAFETY_MAX_PROMPT_CHARS: int = 2000
    SAFETY_EXTRA_BLOCKED_TERMS: str = ""  # comma-separated extra terms

    # ---------- helpers ----------

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def jwt_secret_effective(self) -> str:
        """Dev/test fallback: ephemeral per-process secret (safe but short-lived)."""
        if self.JWT_SECRET:
            return self.JWT_SECRET
        if self.APP_ENV == "production":
            raise RuntimeError(
                "JWT_SECRET is required when APP_ENV=production. "
                'Generate one: python -c "import secrets; print(secrets.token_hex(32))"'
            )
        import secrets as _secrets

        return _secrets.token_hex(32)

    @property
    def extra_blocked_terms_list(self) -> list[str]:
        return [t.strip().lower() for t in self.SAFETY_EXTRA_BLOCKED_TERMS.split(",") if t.strip()]

    @property
    def s3_configured(self) -> bool:
        return bool(self.S3_ENDPOINT and self.S3_BUCKET and self.S3_ACCESS_KEY and self.S3_SECRET_KEY)


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton (re-read on process restart)."""
    return Settings()


settings = get_settings()
