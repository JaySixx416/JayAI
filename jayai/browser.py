"""Ephemeral, read-only browser on explicit HTTPS host allowlist."""

import ipaddress
from urllib.parse import urlsplit
from uuid import UUID

from jayai.contracts import PermissionSpec, PolicyMode, Risk, ToolSpec
from jayai.registry import Registry


def allowed_url(url: str, hosts: frozenset[str]) -> bool:
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        if not hostname or parsed.scheme.lower() != "https" or parsed.username or parsed.password:
            return False
        if parsed.port not in (None, 443) or hostname.lower() not in hosts:
            return False
        if hostname.lower() == "localhost" or hostname.lower().endswith(".local"):
            return False
        try:
            ipaddress.ip_address(hostname)
            return False
        except ValueError:
            return True
    except ValueError:
        return False


def read_page(url: str, hosts: frozenset[str]) -> dict:
    if not allowed_url(url, hosts):
        raise PermissionError("URL not on browser allowlist")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(service_workers="block", accept_downloads=False, java_script_enabled=False)

            def guard(route) -> None:
                if allowed_url(route.request.url, hosts):
                    route.continue_()
                else:
                    route.abort()

            context.route("**/*", guard)
            page = context.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=10000)
            if response is None or not allowed_url(page.url, hosts):
                raise PermissionError("Navigation left browser allowlist")
            return {"url": page.url, "title": page.title()[:500],
                    "text": page.locator("body").inner_text(timeout=5000)[:20000]}
        finally:
            browser.close()


def register_browser_tool(registry: Registry, allowed_hosts: set[str]) -> None:
    hosts = frozenset(h.lower().strip() for h in allowed_hosts if h.strip())
    if not hosts or any("/" in h or ":" in h or "*" in h for h in hosts):
        raise ValueError("Specify exact browser hostnames")
    registry.register(
        ToolSpec(
            id="browser.read_page", description="Read a public HTTPS page on an allowed hostname",
            input_schema={"type": "object", "properties": {"url": {"type": "string", "maxLength": 2048}},
                          "required": ["url"], "additionalProperties": False},
            output_schema={"type": "object", "properties": {"url": {"type": "string"},
                           "title": {"type": "string"}, "text": {"type": "string"}},
                           "required": ["url", "title", "text"], "additionalProperties": False},
            permission=PermissionSpec(resource="browser.public", actions=["read"], risk=Risk.LOW,
                                      mode=PolicyMode.APPROVE_SCOPE), timeout_seconds=30, max_retries=0,
        ),
        lambda _user_id, args: read_page(args["url"], hosts),
    )
