from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Environments that run without TLS and may keep the placeholder secret.
# Anything else is treated as deployed and held to the real-secret rule.
LOCAL_ENVIRONMENTS = frozenset({"local", "development"})

# The checked-in placeholder. It is public, so a cookie signed with it is
# forgeable by anyone who has read the repo.
PLACEHOLDER_SECRET_KEY = "change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    SECRET_KEY: str = PLACEHOLDER_SECRET_KEY
    ENVIRONMENT: str = "local"

    @property
    def is_local(self) -> bool:
        return self.ENVIRONMENT.strip().lower() in LOCAL_ENVIRONMENTS

    @model_validator(mode="after")
    def _reject_the_placeholder_secret_outside_local(self) -> "Settings":
        """Refuse to boot a deployed app with the public placeholder key.

        SECRET_KEY signs the session cookie, which is the only thing tying a
        request to a student_id. With the placeholder, anyone could mint a
        session for any student — so this fails at startup rather than serving
        traffic that merely looks authenticated.
        """
        if not self.is_local and self.SECRET_KEY == PLACEHOLDER_SECRET_KEY:
            raise ValueError(
                f"SECRET_KEY is still the placeholder {PLACEHOLDER_SECRET_KEY!r} but "
                f"ENVIRONMENT is {self.ENVIRONMENT!r}. Session cookies signed with the "
                "public placeholder can be forged. Generate a real one, e.g. "
                '`python -c "import secrets; print(secrets.token_urlsafe(32))"`, '
                "and set SECRET_KEY in the environment."
            )
        return self


settings = Settings()
