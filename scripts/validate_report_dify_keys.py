#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests

PROFILE_ENV = {
    "quick": "DIFY_REPORT_QUICK_APP_API_KEY",
    "standard": "DIFY_REPORT_STANDARD_APP_API_KEY",
    "deep": "DIFY_REPORT_DEEP_APP_API_KEY",
    "research": "DIFY_REPORT_RESEARCH_APP_API_KEY",
}


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip().strip('"').strip("'")
        os.environ[key] = value


def dify_base_url() -> str:
    base = (os.environ.get("DIFY_BASE_URL") or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("DIFY_BASE_URL is not configured")
    if base.endswith("/v1"):
        return base[:-3]
    return base


def validate_profile(profile: str, timeout: int) -> tuple[bool, str]:
    env_var = PROFILE_ENV[profile]
    api_key = (os.environ.get(env_var) or "").strip()
    if not api_key:
        return False, f"{profile}: missing {env_var}"
    try:
        response = requests.get(
            f"{dify_base_url()}/v1/parameters",
            headers={"Authorization": f"Bearer {api_key}", "Host": "localhost"},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return False, f"{profile}: request failed: {type(exc).__name__}: {str(exc)[:200]}"
    if response.status_code != 200:
        return False, f"{profile}: /v1/parameters status={response.status_code} key_len={len(api_key)}"
    return True, f"{profile}: /v1/parameters status=200 key_len={len(api_key)}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Dify report app API keys without printing secrets.")
    parser.add_argument("--env-file", default=".env", help="env file to load before validation")
    parser.add_argument("--profiles", nargs="+", default=["quick", "standard", "deep"], choices=sorted(PROFILE_ENV))
    parser.add_argument("--timeout", type=int, default=10)
    args = parser.parse_args()

    load_env_file(Path(args.env_file))
    ok = True
    for profile in args.profiles:
        profile_ok, message = validate_profile(profile, timeout=args.timeout)
        ok = ok and profile_ok
        print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
