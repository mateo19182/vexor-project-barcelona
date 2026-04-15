from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    clay_api_key: str = ""
    openrouter_api_key: str = ""

    # Paths to the sibling Osintgram tool and its venv. Defaults assume the
    # monorepo layout: backend/ and Osintgram/ share a common parent.
    osintgram_root: str = "../Osintgram"
    osintgram_python: str = "../Osintgram/venv/bin/python"
    # Shared Osintgram output dir (keyed by IG handle). Reused across cases so
    # we don't re-download the same target. Delete a handle's subdir to force
    # a refresh.
    osintgram_output_dir: str = "../Osintgram/output"


settings = Settings()
