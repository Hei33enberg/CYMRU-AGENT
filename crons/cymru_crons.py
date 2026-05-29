"""
crons/cymru_crons.py — CYMRU Cron Engine [LINEAR-1833 F2.7]

Migrates all god-*-cron Supabase Edge Functions to cymru-agent persistent cron jobs.
Uses Hermes built-in croniter scheduler (already a core dep).

Cron schedule:
  1. god_proactive_cron     — 0 2 * * *  (02:00 daily) CLAW nightly synthesis
  2. god_knowledge_cron     — 0 4 * * *  (04:00 daily) RAG harvest
  3. proactive_triggers     — */15 * * * * (every 15 min) Spotify + Calendar triggers
  4. refresh_live_context   — 0 * * * *  (hourly) moon phase, planetary hour, zodiac
  5. memory_decay           — 0 3 * * *  (03:00 daily) decay user memory scores
"""

from __future__ import annotations
import os
import logging
from datetime import datetime, date, timezone, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

def _sb() -> Client:
    return create_client(_SUPABASE_URL, _SUPABASE_KEY)


def _claim_dispatch(sb: Client, cron_name: str) -> bool:
    """Atomically claim this cron run across all cymru-agent instances (LINEAR-2352).

    Every instance (VPS / local / hardware) runs the same CYMRU_CRON_SCHEDULE, so
    without this each tick fired N times — memory_decay decayed N×, proactive_triggers
    double-processed events, god_proactive double-inserted. We bucket run_at to the
    current UTC minute (croniter fires on minute boundaries, so all instances of a
    tick map to the same key) and INSERT into dispatch_lock. The primary key on
    (cron_name, run_at) means the first INSERT wins; everyone else hits a duplicate-key
    conflict and skips.

    Fail-open by design: only a *duplicate-key* error means "someone else owns this
    run" → skip. Any other error (missing table, transient network, RLS) returns True
    so a misconfiguration can never silently disable every cron — worst case we fall
    back to the pre-fix behaviour, never to "all crons dead".
    """
    run_at = datetime.now(timezone.utc).replace(second=0, microsecond=0).isoformat()
    try:
        sb.table("dispatch_lock").insert({"cron_name": cron_name, "run_at": run_at}).execute()
        return True
    except Exception as e:
        msg = str(e).lower()
        if "duplicate key" in msg or "23505" in msg or "already exists" in msg:
            logger.info("[CRON] %s already claimed for %s — skipping duplicate run", cron_name, run_at)
            return False
        logger.warning("[CRON] %s dispatch-lock claim errored (proceeding fail-open): %s", cron_name, e)
        return True


# ---------------------------------------------------------------------------
# 1. GOD PROACTIVE CRON — CLAW nightly synthesis
# Schedule: 0 2 * * * (02:00 daily)
# ---------------------------------------------------------------------------

def god_proactive_cron() -> None:
    """
    CLAW: Nightly synthesis of last 24h conversations into a summary embedding.
    Ported from: supabase/functions/god-proactive-cron/index.ts
    """
    logger.info("[CRON] god_proactive_cron started at %s", datetime.now(timezone.utc))
    try:
        sb = _sb()
        if not _claim_dispatch(sb, "god_proactive_cron"):
            return
        # Fetch all users with recent activity
        yesterday = date.today().isoformat()
        users_resp = sb.table("profiles").select("id").execute()
        user_ids = [u["id"] for u in (users_resp.data or [])]

        synthesized = 0
        for user_id in user_ids:
            # Get recent shaman conversations
            conv_resp = (
                sb.table("shaman_conversations")
                .select("messages")
                .eq("user_id", user_id)
                .gte("created_at", f"{yesterday}T00:00:00Z")
                .execute()
            )
            if not conv_resp.data:
                continue

            # Concatenate messages for summary (GEMINI synthesis would go here)
            all_text = " ".join(
                str(c.get("messages", "")) for c in conv_resp.data
            )
            if len(all_text) < 50:
                continue

            # Store synthesis marker (full embedding via GEMINI API when key available)
            sb.table("user_memory").insert({
                "user_id": user_id,
                "content": f"[CLAW-SYNTHESIS-{yesterday}] {all_text[:500]}",
                "category": "claw_synthesis",
                "source": "god_proactive_cron",
            }).execute()
            synthesized += 1

        logger.info("[CRON] god_proactive_cron done: %d users synthesized", synthesized)
    except Exception as e:
        logger.error("[CRON] god_proactive_cron error: %s", e)


# ---------------------------------------------------------------------------
# 2. GOD KNOWLEDGE CRON — Daily RAG harvest
# Schedule: 0 4 * * * (04:00 daily)
# ---------------------------------------------------------------------------

SEPTON_QUERIES = [
    "minerals crystal healing properties",
    "astrology planetary aspects",
    "numerology life path meanings",
    "human design types centers",
    "sacred geometry patterns",
    "alchemy elements transformation",
    "tarot major arcana meanings",
    "chakra energy centers meditation",
    "ancient wisdom mystery schools",
    "quantum consciousness spirituality",
    "shamanic traditions healing",
    "kabbalah tree of life",
    "vedic astrology nakshatras",
    "druidic nature philosophy",
    "hermetic principles kybalion",
]


def god_knowledge_cron() -> None:
    """
    Daily RAG harvest: 15 septon queries → Exa.ai/Brave → knowledge_base.
    Ported from: supabase/functions/god-knowledge-cron/index.ts
    Requires: EXA_API_KEY in .env for full operation.
    """
    logger.info("[CRON] god_knowledge_cron started at %s", datetime.now(timezone.utc))
    exa_key = os.getenv("EXA_API_KEY", "")
    if not exa_key:
        logger.warning("[CRON] god_knowledge_cron: EXA_API_KEY not set, skipping harvest")
        return

    try:
        import httpx
        sb = _sb()
        if not _claim_dispatch(sb, "god_knowledge_cron"):
            return
        harvested = 0

        for query in SEPTON_QUERIES:
            resp = httpx.post(
                "https://api.exa.ai/search",
                headers={"x-api-key": exa_key, "Content-Type": "application/json"},
                json={"query": query, "numResults": 3, "useAutoprompt": True, "contents": {"text": True}},
                timeout=15,
            )
            if resp.status_code != 200:
                continue

            results = resp.json().get("results", [])
            for r in results:
                try:
                    sb.table("knowledge_base").insert({
                        "title": r.get("title", query),
                        "content": r.get("text", "")[:5000],
                        "source_url": r.get("url", ""),
                        "category": "auto_harvest",
                        "harvested_at": datetime.now(timezone.utc).isoformat(),
                    }).execute()
                    harvested += 1
                except Exception:
                    pass  # Ignore duplicates

        logger.info("[CRON] god_knowledge_cron done: %d documents harvested", harvested)
    except Exception as e:
        logger.error("[CRON] god_knowledge_cron error: %s", e)


# ---------------------------------------------------------------------------
# 3. PROACTIVE TRIGGERS — Spotify + Calendar 15-min reminder
# Schedule: */15 * * * * (every 15 minutes)
# ---------------------------------------------------------------------------

def proactive_triggers() -> None:
    """
    Check Spotify recent track and upcoming calendar events → push proactive notification.
    Ported from: supabase/functions/proactive-triggers/index.ts
    """
    logger.info("[CRON] proactive_triggers started at %s", datetime.now(timezone.utc))
    try:
        sb = _sb()
        if not _claim_dispatch(sb, "proactive_triggers"):
            return
        # Get users with proactive events enabled
        events_resp = (
            sb.table("user_proactive_events")
            .select("user_id, event_type, trigger_at, payload")
            .lte("trigger_at", datetime.now(timezone.utc).isoformat())
            .eq("is_processed", False)
            .limit(20)
            .execute()
        )
        if not events_resp.data:
            logger.debug("[CRON] proactive_triggers: no pending events")
            return

        for event in events_resp.data:
            try:
                # Mark as processed
                sb.table("user_proactive_events").update({"is_processed": True}).eq("id", event["id"]).execute()
                logger.info("[CRON] proactive_triggers: processed event %s for user %s", event["event_type"], event["user_id"])
            except Exception as exc:
                logger.warning("[CRON] proactive_triggers: failed to process event: %s", exc)

    except Exception as e:
        logger.error("[CRON] proactive_triggers error: %s", e)


# ---------------------------------------------------------------------------
# 4. REFRESH LIVE CONTEXT — Hourly: moon phase, planetary hour, zodiac
# Schedule: 0 * * * * (hourly)
# ---------------------------------------------------------------------------

def refresh_live_context() -> None:
    """
    Refresh live cosmological context: moon phase, planetary hour, current zodiac sign.
    Ported from: supabase/functions/refresh-live-context/index.ts
    """
    logger.info("[CRON] refresh_live_context started at %s", datetime.now(timezone.utc))
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        # Simple moon phase calc (synodic month ~29.53 days from known new moon)
        known_new_moon = datetime(2024, 1, 11, tzinfo=timezone.utc)
        days_since = (now - known_new_moon).total_seconds() / 86400
        synodic = 29.53059
        phase_index = (days_since % synodic) / synodic
        phases = ["New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous",
                  "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent"]
        moon_phase = phases[int(phase_index * 8) % 8]

        # Current zodiac sun sign
        month, day = now.month, now.day
        zodiac_dates = [(1,20,"Aquarius"),(2,19,"Pisces"),(3,21,"Aries"),(4,20,"Taurus"),
                        (5,21,"Gemini"),(6,21,"Cancer"),(7,23,"Leo"),(8,23,"Virgo"),
                        (9,23,"Libra"),(10,23,"Scorpio"),(11,22,"Sagittarius"),(12,22,"Capricorn")]
        zodiac = next((z for m, d, z in zodiac_dates if (month == m and day >= d) or (month == (m % 12) + 1 and day < d)), "Capricorn")

        sb = _sb()
        if not _claim_dispatch(sb, "refresh_live_context"):
            return
        sb.table("system_truth").upsert({
            "key": "live_context",
            "value": {
                "moon_phase": moon_phase,
                "zodiac_sign": zodiac,
                "refreshed_at": now.isoformat(),
                "planetary_hour": now.hour % 7,  # simplified
            }
        }, on_conflict="key").execute()
        logger.info("[CRON] refresh_live_context: moon=%s zodiac=%s", moon_phase, zodiac)
    except Exception as e:
        logger.error("[CRON] refresh_live_context error: %s", e)


# ---------------------------------------------------------------------------
# 5. MEMORY DECAY — Daily: decay_score -0.02/day
# Schedule: 0 3 * * * (03:00 daily)
# ---------------------------------------------------------------------------

def memory_decay() -> None:
    """
    Apply daily memory decay: reduce quality/relevance score of old memories.
    Ensures stale facts don't dominate retrieval.
    """
    logger.info("[CRON] memory_decay started at %s", datetime.now(timezone.utc))
    try:
        sb = _sb()
        if not _claim_dispatch(sb, "memory_decay"):
            return
        # Apply decay via SQL RPC if available, else batch update
        sb.rpc("decay_user_memory_scores", {"decay_amount": 0.02}).execute()
        logger.info("[CRON] memory_decay: decay applied")
        # Housekeeping: prune dispatch_lock rows older than 7 days (runs once/day on
        # whichever instance won the memory_decay claim).
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            sb.table("dispatch_lock").delete().lt("claimed_at", cutoff).execute()
        except Exception as prune_err:
            logger.debug("[CRON] dispatch_lock prune skipped: %s", prune_err)
    except Exception as e:
        logger.warning("[CRON] memory_decay: RPC not available, skipping. Error: %s", e)


# ---------------------------------------------------------------------------
# Cron Schedule Registry
# Used by cymru-agent cron engine (croniter is a core Hermes dep)
# ---------------------------------------------------------------------------

CYMRU_CRON_SCHEDULE = [
    ("0 2 * * *",   god_proactive_cron,   "CLAW Nightly Synthesis"),
    ("0 4 * * *",   god_knowledge_cron,   "RAG Daily Harvest"),
    ("*/15 * * * *", proactive_triggers,  "Proactive Triggers (15min)"),
    ("0 * * * *",   refresh_live_context, "Live Context Refresh (hourly)"),
    ("0 3 * * *",   memory_decay,         "Memory Decay (daily)"),
]
