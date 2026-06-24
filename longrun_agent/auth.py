"""Authentication storage for LongRun Agent.

Stage 2 keeps auth deliberately small: OpenAI API keys and the Codex OAuth token
shape are stored, inspected, and cleared. The actual Codex login exchange can be
added on top of this without changing callers.
"""

from __future__ import annotations

import json
import os
import base64
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path
from typing import Any

from longrun_agent.config import DEFAULT_CODEX_MODEL, auth_path, ensure_home, env_path

AUTH_STORE_VERSION = 1
OPENAI_API_PROVIDER = "openai-api"
CODEX_PROVIDER = "openai-codex"
CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_OAUTH_ISSUER = "https://auth.openai.com"
CODEX_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
DEFAULT_CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"


@dataclass(frozen=True)
class ProviderStatus:
    """Redacted auth status for one provider."""

    provider: str
    configured: bool
    source: str | None = None
    detail: str | None = None


def load_auth_store() -> dict[str, Any]:
    """Load `auth.json`, returning an empty versioned store if missing."""

    path = auth_path()
    if not path.exists():
        return {"version": AUTH_STORE_VERSION, "providers": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid auth store: {path}")
    data.setdefault("version", AUTH_STORE_VERSION)
    data.setdefault("providers", {})
    return data


def save_auth_store(store: dict[str, Any]) -> Path:
    """Write `auth.json` with restrictive local intent."""

    ensure_home()
    path = auth_path()
    store["version"] = AUTH_STORE_VERSION
    store.setdefault("providers", {})
    path.write_text(json.dumps(store, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def read_env_file(path: Path | None = None) -> dict[str, str]:
    """Read the small `.env` format used for secrets."""

    target = path or env_path()
    if not target.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def get_openai_api_key() -> tuple[str | None, str | None]:
    """Return the OpenAI API key and where it came from."""

    env_value = os.environ.get("OPENAI_API_KEY")
    if env_value:
        return env_value, "environment"

    env_file_value = read_env_file().get("OPENAI_API_KEY")
    if env_file_value:
        return env_file_value, ".env"

    provider = load_auth_store().get("providers", {}).get(OPENAI_API_PROVIDER, {})
    api_key = provider.get("api_key")
    if isinstance(api_key, str) and api_key:
        return api_key, "auth.json"
    return None, None


def set_openai_api_key(api_key: str | None = None) -> Path:
    """Persist an OpenAI API key in `auth.json`."""

    key = api_key or getpass("OpenAI API key: ").strip()
    if not key:
        raise ValueError("OpenAI API key cannot be empty")

    store = load_auth_store()
    providers = store.setdefault("providers", {})
    providers[OPENAI_API_PROVIDER] = {
        "api_key": key,
        "updated_at": _now_iso(),
    }
    return save_auth_store(store)


def set_codex_tokens(
    *,
    access_token: str,
    refresh_token: str | None = None,
    account_id: str | None = None,
    expires_at: str | None = None,
) -> Path:
    """Persist Codex OAuth tokens.

    This is the storage boundary only. The browser/device-code login flow will
    later call this after exchanging or refreshing tokens.
    """

    if not access_token.strip():
        raise ValueError("Codex access token cannot be empty")

    store = load_auth_store()
    providers = store.setdefault("providers", {})
    providers[CODEX_PROVIDER] = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "account_id": account_id,
        "expires_at": expires_at,
        "updated_at": _now_iso(),
    }
    return save_auth_store(store)


def login_codex_device_code(*, open_browser: bool = True, timeout_seconds: int = 900) -> Path:
    """Run OpenAI Codex browser/device-code login and store OAuth tokens."""

    device_data = _request_codex_device_code()
    user_code = str(device_data.get("user_code") or "")
    device_auth_id = str(device_data.get("device_auth_id") or "")
    poll_interval = max(3, int(device_data.get("interval") or 5))
    verification_url = f"{CODEX_OAUTH_ISSUER}/codex/device"

    if not user_code or not device_auth_id:
        raise RuntimeError("Codex device-code response was missing required fields")

    print("To continue, sign in with your ChatGPT/Codex account.")
    print("")
    print("  1. Open this URL in your browser:")
    print(f"     {verification_url}")
    print("")
    print("  2. Enter this code:")
    print(f"     {user_code}")
    print("")
    if open_browser:
        try:
            if webbrowser.open(verification_url):
                print("  Browser opened for verification.")
            else:
                print("  Could not open browser automatically; use the URL above.")
        except Exception:
            print("  Could not open browser automatically; use the URL above.")
    print("Waiting for browser approval... press Ctrl+C to cancel.")

    code_payload = _poll_codex_device_code(
        device_auth_id=device_auth_id,
        user_code=user_code,
        poll_interval=poll_interval,
        timeout_seconds=timeout_seconds,
    )
    token_payload = _exchange_codex_authorization_code(
        authorization_code=str(code_payload.get("authorization_code") or ""),
        code_verifier=str(code_payload.get("code_verifier") or ""),
    )
    access_token = str(token_payload.get("access_token") or "")
    refresh_token = str(token_payload.get("refresh_token") or "")
    if not access_token:
        raise RuntimeError("Codex token exchange did not return an access token")

    return set_codex_tokens(
        access_token=access_token,
        refresh_token=refresh_token or None,
        expires_at=_jwt_exp_iso(access_token),
    )


def import_codex_cli_tokens() -> Path:
    """Import existing Codex CLI OAuth tokens from `~/.codex/auth.json`."""

    tokens = read_codex_cli_tokens()
    if not tokens:
        raise RuntimeError("No usable Codex CLI tokens found at CODEX_HOME/auth.json or ~/.codex/auth.json")
    return set_codex_tokens(
        access_token=str(tokens["access_token"]),
        refresh_token=str(tokens.get("refresh_token") or ""),
        account_id=str(tokens.get("account_id") or "") or None,
        expires_at=str(tokens.get("expires_at") or "") or None,
    )


def read_codex_cli_tokens() -> dict[str, Any] | None:
    """Read non-expired Codex CLI tokens without mutating the Codex CLI file."""

    codex_home = os.environ.get("CODEX_HOME", "").strip()
    auth_file = Path(codex_home).expanduser() / "auth.json" if codex_home else Path.home() / ".codex" / "auth.json"
    if not auth_file.is_file():
        return None

    try:
        payload = json.loads(auth_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    tokens = payload.get("tokens")
    if not isinstance(tokens, dict):
        return None
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    if not isinstance(access_token, str) or not access_token:
        return None
    if not isinstance(refresh_token, str) or not refresh_token:
        return None
    if _jwt_is_expired(access_token):
        return None

    imported = dict(tokens)
    imported.setdefault("expires_at", _jwt_exp_iso(access_token))
    return imported


def clear_provider(provider: str) -> bool:
    """Remove one provider from `auth.json`."""

    store = load_auth_store()
    providers = store.setdefault("providers", {})
    existed = provider in providers
    providers.pop(provider, None)
    save_auth_store(store)
    return existed


def get_provider_statuses() -> list[ProviderStatus]:
    """Return redacted auth status for supported providers."""

    openai_key, openai_source = get_openai_api_key()
    codex = load_auth_store().get("providers", {}).get(CODEX_PROVIDER, {})
    codex_access = codex.get("access_token")
    codex_detail = None
    if codex.get("expires_at"):
        codex_detail = f"expires_at={codex['expires_at']}"
    elif codex_access:
        codex_detail = "token stored; expiry unknown"

    return [
        ProviderStatus(
            provider=OPENAI_API_PROVIDER,
            configured=bool(openai_key),
            source=openai_source,
            detail=_mask_secret(openai_key) if openai_key else None,
        ),
        ProviderStatus(
            provider=CODEX_PROVIDER,
            configured=bool(codex_access),
            source="auth.json" if codex_access else None,
            detail=codex_detail,
        ),
    ]


def require_openai_api_key() -> str:
    """Return an OpenAI API key or raise a clear setup error."""

    api_key, _source = get_openai_api_key()
    if not api_key:
        raise RuntimeError(
            "OpenAI API key is not configured. Use `longrun auth set-openai-key` "
            "or set OPENAI_API_KEY in the environment or .env file."
        )
    return api_key


def get_codex_access_token() -> str | None:
    """Return a stored Codex access token if present."""

    provider = load_auth_store().get("providers", {}).get(CODEX_PROVIDER, {})
    token = provider.get("access_token")
    return token if isinstance(token, str) and token else None


def get_codex_runtime_credentials() -> dict[str, str]:
    """Return Codex credentials or import them from Codex CLI if possible."""

    provider = load_auth_store().get("providers", {}).get(CODEX_PROVIDER, {})
    token = provider.get("access_token")
    if isinstance(token, str) and token:
        return {
            "access_token": token,
            "base_url": DEFAULT_CODEX_BASE_URL,
            "model": DEFAULT_CODEX_MODEL,
            "source": "auth.json",
        }

    imported = read_codex_cli_tokens()
    if imported:
        set_codex_tokens(
            access_token=str(imported["access_token"]),
            refresh_token=str(imported.get("refresh_token") or ""),
            account_id=str(imported.get("account_id") or "") or None,
            expires_at=str(imported.get("expires_at") or "") or None,
        )
        return {
            "access_token": str(imported["access_token"]),
            "base_url": DEFAULT_CODEX_BASE_URL,
            "model": DEFAULT_CODEX_MODEL,
            "source": "codex-cli",
        }

    raise RuntimeError(
        "Codex OAuth is not configured. Run `longrun auth login-codex` "
        "or `longrun auth import-codex-cli` first."
    )


def _request_codex_device_code() -> dict[str, Any]:
    return _json_request(
        f"{CODEX_OAUTH_ISSUER}/api/accounts/deviceauth/usercode",
        json_body={"client_id": CODEX_OAUTH_CLIENT_ID},
        error_context="request Codex device code",
    )


def _poll_codex_device_code(
    *,
    device_auth_id: str,
    user_code: str,
    poll_interval: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        try:
            return _json_request(
                f"{CODEX_OAUTH_ISSUER}/api/accounts/deviceauth/token",
                json_body={"device_auth_id": device_auth_id, "user_code": user_code},
                error_context="poll Codex device authorization",
            )
        except RuntimeError as exc:
            text = str(exc)
            if "HTTP 403" in text or "HTTP 404" in text:
                continue
            raise
    raise TimeoutError("Codex browser approval timed out")


def _exchange_codex_authorization_code(*, authorization_code: str, code_verifier: str) -> dict[str, Any]:
    if not authorization_code or not code_verifier:
        raise RuntimeError("Codex approval response was missing authorization_code or code_verifier")
    return _json_request(
        CODEX_OAUTH_TOKEN_URL,
        form_body={
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": f"{CODEX_OAUTH_ISSUER}/deviceauth/callback",
            "client_id": CODEX_OAUTH_CLIENT_ID,
            "code_verifier": code_verifier,
        },
        error_context="exchange Codex authorization code",
    )


def _json_request(
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
    form_body: dict[str, str] | None = None,
    error_context: str,
) -> dict[str, Any]:
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        content_type = "application/json"
    elif form_body is not None:
        body = urllib.parse.urlencode(form_body).encode("utf-8")
        content_type = "application/x-www-form-urlencoded"
    else:
        body = b""
        content_type = "application/json"

    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": content_type, "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Failed to {error_context}: HTTP {exc.code}. {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to {error_context}: {exc.reason}") from exc

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to {error_context}: response was not JSON") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Failed to {error_context}: response was not a JSON object")
    return data


def _mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jwt_exp_iso(token: str) -> str | None:
    exp = _jwt_exp(token)
    if exp is None:
        return None
    return datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()


def _jwt_is_expired(token: str) -> bool:
    exp = _jwt_exp(token)
    if exp is None:
        return False
    return exp <= datetime.now(timezone.utc).timestamp()


def _jwt_exp(token: str) -> int | None:
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode((payload + padding).encode("ascii"))
        data = json.loads(decoded.decode("utf-8"))
    except Exception:
        return None
    exp = data.get("exp")
    return int(exp) if isinstance(exp, int | float) else None
