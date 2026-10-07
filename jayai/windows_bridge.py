"""Bounded, authenticated request through the Chromebook-to-Windows SSH tunnel."""

import os

import httpx


def diagnostics(transport: httpx.BaseTransport | None = None) -> dict:
    key = os.getenv("JAYAI_COMPANION_KEY", "")
    if len(key) < 32:
        raise RuntimeError("Windows companion key is not configured")
    try:
        with httpx.Client(timeout=60, transport=transport, trust_env=False) as client:
            response = client.get("http://127.0.0.1:8765/v1/diagnostics",
                                  headers={"Authorization": "Bearer " + key})
            if response.status_code == 401:
                raise RuntimeError("Windows companion key does not match")
            response.raise_for_status()
            if len(response.content) > 65536:
                raise ValueError("Windows diagnostics too large")
            data = response.json()
    except httpx.ConnectError as exc:
        raise RuntimeError("Windows companion tunnel unavailable") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError("Windows diagnostics request failed") from exc
    if not isinstance(data, dict) or data.get("scope") != "Windows laptop" or \
            type(data.get("free_percent")) not in (int, float) or not 0 <= data["free_percent"] <= 100 or \
            not all(isinstance(data.get(k), list) for k in ("startup", "recent_errors", "package_updates", "findings")) or \
            data.get("applied_changes") != []:
        raise ValueError("Windows companion response is invalid")
    return data
