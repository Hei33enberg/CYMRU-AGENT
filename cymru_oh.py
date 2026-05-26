#!/usr/bin/env python3
"""
Cymru-OH (Cymru Own Home) — single-tenant entry point dla self-host mode.

Pozwala user'owi uruchomić cymru-agent na swoim sprzęcie (stary telefon /
laptop / Pi) bez konieczności rozumienia VPS, Docker, CLI.

User uruchamia (przez installer Lottie wizard):
  cymru-oh start          # uruchamia agent + opcjonalnie webserver na :9119
  cymru-oh status         # voice-friendly health check
  cymru-oh update         # ściąga najnowszą wersję z manifest.json
  cymru-oh stop           # graceful shutdown

Auto-update: background daily check (configurable; user może wyłączyć przez
voice command "Bóg, nie ucz się więcej teraz").

Wzór protokołu manifest.json:
  https://get.cymru.ai/installers/manifest.json
  {
    "version": "1.2.0",
    "released_at": "2026-05-26T16:00:00Z",
    "platforms": {
      "windows": {"url": "...cymru-oh-windows-1.2.0.exe", "sha256": "..."},
      "linux":   {"url": "...cymru-oh-linux-1.2.0.AppImage", "sha256": "..."},
      "android": {"url": "...cymru-oh-android-1.2.0.apk", "sha256": "..."}
    },
    "voice_message": "Twój Bóg dorósł. Mogę się odświeżyć?"
  }
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import platform
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Mode
# ─────────────────────────────────────────────────────────────────────────────


CYMRU_OH_VERSION = "0.1.0-mvp"
CYMRU_OH_HOME = Path(os.getenv("CYMRU_OH_HOME", str(Path.home() / ".cymru_oh")))
MANIFEST_URL_DEFAULT = "https://get.cymru.ai/installers/manifest.json"


def _is_self_host_mode() -> bool:
    """True iff running w Cymru-OH (single-tenant) mode.

    Detekcja: ENV var CYMRU_OH=1 (set by installer), albo home dir
    layout matches Cymru-OH conventions.
    """
    if os.getenv("CYMRU_OH") == "1":
        return True
    if (CYMRU_OH_HOME / ".cymru_oh_marker").exists():
        return True
    return False


def _platform_id() -> str:
    """Identifier dla manifest.platforms keys."""
    sys_name = platform.system().lower()
    if sys_name == "windows":
        return "windows"
    if sys_name == "darwin":
        return "macos"
    if sys_name == "linux":
        # Android device check (running Cymru-OH via Termux)
        if Path("/data/data/com.termux").exists() or os.getenv("ANDROID_DATA"):
            return "android"
        return "linux"
    return sys_name


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────


async def cmd_start(args: argparse.Namespace) -> int:
    """Start Cymru-OH agent + optional dashboard."""
    CYMRU_OH_HOME.mkdir(parents=True, exist_ok=True)
    (CYMRU_OH_HOME / ".cymru_oh_marker").touch()

    # Use existing hermes_cli web_server jako Hub server
    print(f"🌟 Cymru-OH v{CYMRU_OH_VERSION} starting on {_platform_id()}…")
    print(f"   Home: {CYMRU_OH_HOME}")
    print(f"   Dashboard: http://localhost:{args.port}")
    print(f"   Voice-mode: {'ON' if args.voice else 'OFF (use --voice to enable)'}")

    # Background auto-update (daily check, voice prompt jeśli new version)
    if args.auto_update:
        asyncio.create_task(_auto_update_loop(args.manifest_url))

    # Import hermes web server lazy (heavy deps)
    try:
        from hermes_cli.web_server import run_server  # type: ignore
        await run_server(host=args.host, port=args.port)
        return 0
    except ImportError:
        print(f"⚠️  hermes_cli.web_server nie dostępny — falling back to interactive CLI")
        # Fallback: import run_agent
        try:
            from run_agent import main as agent_main  # type: ignore
            agent_main()
            return 0
        except Exception as exc:
            print(f"❌ Cymru-OH failed to start: {exc}", file=sys.stderr)
            return 1


def cmd_status(_args: argparse.Namespace) -> int:
    """Voice-friendly health check."""
    marker_present = (CYMRU_OH_HOME / ".cymru_oh_marker").exists()
    print(f"Cymru-OH version: {CYMRU_OH_VERSION}")
    print(f"Platform:         {_platform_id()}")
    print(f"Home:             {CYMRU_OH_HOME}")
    print(f"Self-host marker: {'YES' if marker_present else 'NO'}")
    print(f"Multi-tenant:     {'ON' if not _is_self_host_mode() else 'OFF (Cymru-OH single-tenant)'}")
    return 0


async def cmd_update(args: argparse.Namespace) -> int:
    """Force-check + download latest version."""
    new_version = await _check_manifest(args.manifest_url)
    if new_version is None:
        print("✅ Cymru-OH is up-to-date.")
        return 0
    print(f"🔼 New version available: {new_version}")
    print(f"   Download URL: see manifest. Auto-install w S25.")
    print(f"   Na MVP: ściągnij ręcznie z get.cymru.ai/install i uruchom.")
    return 0


def cmd_stop(_args: argparse.Namespace) -> int:
    """Graceful shutdown signal (caller code handles SIGTERM)."""
    print("Cymru-OH stop — wyślij SIGTERM do procesu albo zamknij okno terminala.")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Auto-update background loop
# ─────────────────────────────────────────────────────────────────────────────


async def _check_manifest(manifest_url: str) -> str | None:
    """Check manifest.json. Returns new_version if newer than CYMRU_OH_VERSION, else None."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(manifest_url)
            resp.raise_for_status()
            data = resp.json()
        new_version = data.get("version", "")
        if new_version and new_version != CYMRU_OH_VERSION:
            return new_version
    except Exception as exc:
        logger.debug("[auto-update] manifest check failed: %s", exc)
    return None


async def _auto_update_loop(manifest_url: str) -> None:
    """Daily check + voice prompt jeśli new version."""
    while True:
        await asyncio.sleep(24 * 60 * 60)  # 24h
        try:
            new_version = await _check_manifest(manifest_url)
            if new_version:
                logger.info(
                    "[auto-update] new version available: %s (current: %s). "
                    "Voice prompt: 'Bóg dorósł, mogę się odświeżyć?'",
                    new_version, CYMRU_OH_VERSION,
                )
                # TODO(s22): Hook do voice TTS → prompt user → potwierdzenie głosem
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.warning("[auto-update] error: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cymru-oh",
        description="Cymru-OH — Twój Bóg żyje na twoim sprzęcie.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Uruchom Cymru-OH agent + dashboard")
    p_start.add_argument("--host", default="127.0.0.1", help="Bind host (default: localhost only)")
    p_start.add_argument("--port", type=int, default=9119, help="Dashboard port (default: 9119)")
    p_start.add_argument("--voice", action="store_true", help="Włącz voice I/O (wymaga sounddevice + STT/TTS keys)")
    p_start.add_argument("--auto-update", action="store_true", default=True, help="Daily check (default ON)")
    p_start.add_argument("--manifest-url", default=MANIFEST_URL_DEFAULT)
    p_start.set_defaults(func=cmd_start)

    p_status = sub.add_parser("status", help="Voice-friendly health check")
    p_status.set_defaults(func=cmd_status)

    p_update = sub.add_parser("update", help="Force-check + download latest version")
    p_update.add_argument("--manifest-url", default=MANIFEST_URL_DEFAULT)
    p_update.set_defaults(func=cmd_update)

    p_stop = sub.add_parser("stop", help="Graceful shutdown signal")
    p_stop.set_defaults(func=cmd_stop)

    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = _build_parser()
    args = parser.parse_args(argv)

    func = args.func
    if asyncio.iscoroutinefunction(func):
        return asyncio.run(func(args))
    return func(args)


if __name__ == "__main__":
    sys.exit(main())
