from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=[".env", "../.env"], extra="ignore")

    anthropic_api_key: str = ""
    clay_api_key: str = ""
    openrouter_api_key: str = ""
    # When set, the osint_web module swaps Anthropic's server-side web_search/
    # web_fetch tools for an Exa-backed client-side tool loop (exa_search →
    # search_and_contents). Absent → fall back to the Anthropic web tools.
    exa_api_key: str = ""
    brave_api_key: str = ""
    # SerpAPI key used by the image_search module's google_lens reverse-image
    # lookup. Absent → the module skips cleanly.
    serper_api_key: str = ""
    # HikerAPI token for Osintgram's hikerapi-backed mode. Exported into the
    # subprocess env as HIKERAPI_TOKEN (Osintgram reads it case-sensitive).
    hikerapi_token: str = ""

    # Paths to the sibling Osintgram tool and its venv. Defaults assume the
    # monorepo layout: backend/ and Osintgram/ share a common parent.
    osintgram_root: str = "../Osintgram"
    osintgram_python: str = "../Osintgram/venv/bin/python"
    # Shared Osintgram output dir (keyed by IG handle). Reused across cases so
    # we don't re-download the same target. Delete a handle's subdir to force
    # a refresh.
    osintgram_output_dir: str = "../Osintgram/output"

    # Breach intelligence provider. Host is kept in env so the vendor is not
    # hard-coded anywhere in source. Leave blank to disable the module.
    breach_intel_host: str = ""
    breach_intel_api_key: str = ""

    # Platform-registration check API. One host, one proxy, and per-platform
    # (port, api_key) pairs. Each upstream VM answers /cs (create session) +
    # /h (check handle) over HTTPS on a self-signed cert — see
    # app/enrichment/platform_check.py.
    platform_check_host: str = "163.5.221.166"
    platform_check_proxy: str = ""
    instagram_check_port: str = ""
    instagram_check_api_key: str = ""
    twitter_check_port: str = ""
    twitter_check_api_key: str = ""
    icloud_check_port: str = ""
    icloud_check_api_key: str = ""
    github_check_port: str = "19185"
    github_check_api_key: str = ""

    # Google Photos API key used by the google_id module (GHunt technique).
    # Defaults to the well-known public key; override via GOOGLE_PHOTOS_API_KEY.
    google_photos_api_key: str = "AIzaSyAa2odBewW-sPJu3jMORr0aNedh3YlkiQc"

    # Per-run log directory. Each call to `enrich()` drops a JSON dump of the
    # full response (dossier + modules + audit events) at
    # `{logs_dir}/{case_id}/{timestamp}.json`. Resolved from CWD.
    logs_dir: str = "logs"

    # Nominatim exige User-Agent identificable; incluye contacto real en producción.
    nominatim_user_agent: str = "VexorBCN-Enrichment/0.1 (hackathon; mateoamadoares@gmail.com)"

    catastro_api_key: str = ""

    # ── Twitter/X enrichment (twscrape) ────────────────────────────────────
    # Credentials for a burner Twitter account used by twscrape to fetch
    # public profiles and timelines. Cookie-based auth is more stable —
    # if TWITTER_COOKIES is set (JSON string), it takes precedence.
    twitter_username: str = ""
    twitter_password: str = ""
    twitter_cookies: str = ""  # JSON dict of cookies; overrides password auth

    # ── LinkedIn enrichment (LinkdAPI) ─────────────────────────────────────
    # API key for https://linkdapi.com — used by the `linkedin` module to
    # call /api/v1/profile/overview and /api/v1/profile/details. Blank → the
    # module skips cleanly.
    linkdapi_api_key: str = ""

    # NoSINT CSINT platform — email/username/phone OSINT via 30+ modules.
    # Generate at: https://nosint.org/dashboard/settings (API Keys section).
    nosint_api_key: str = ""

    # ── Google Maps reviews module ──────────────────────────────────────────
    # JSON dict copied from Chrome DevTools → Application → Cookies → google.com
    # Required keys: SID, SSID, APISID, SAPISID, __Secure-1PAPISID, NID
    google_session_cookies: str = ""


settings = Settings()
