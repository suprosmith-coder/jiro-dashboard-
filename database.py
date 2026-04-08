"""
database.py — Jiro Discord Bot
Supabase REST API client using the anon key directly over HTTPS.
No SDK required — avoids all APIError / key validation issues.

Usage in bot.py:
    from database import Database
    bot.db = Database(SUPABASE_URL, SUPABASE_ANON_KEY)
"""

import os
import aiohttp
import json
from typing import Any


# ── Supabase REST headers ──────────────────────────────────────────────────────

def _headers(key: str) -> dict:
    return {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }


# ══════════════════════════════════════════════════════════════════════════════
# Database class
# ══════════════════════════════════════════════════════════════════════════════

class Database:
    """
    Thin async wrapper around Supabase REST API.
    All methods mirror what the Jiro cogs call on `bot.db`.

    Required Supabase tables
    ────────────────────────
    guild_configs   (guild_id TEXT PK, config JSONB)
    mod_logs        (id BIGSERIAL PK, guild_id TEXT, action TEXT,
                     mod_id TEXT, target_id TEXT, reason TEXT,
                     created_at TIMESTAMPTZ DEFAULT now())
    warnings        (id BIGSERIAL PK, guild_id TEXT, user_id TEXT,
                     mod_id TEXT, reason TEXT,
                     created_at TIMESTAMPTZ DEFAULT now())
    bad_words       (guild_id TEXT, word TEXT, PRIMARY KEY (guild_id, word))
    self_roles      (guild_id TEXT, role_id TEXT, PRIMARY KEY (guild_id, role_id))
    shared_mods     (id BIGSERIAL PK, guild_id TEXT, mod_id TEXT,
                     target_id TEXT, action TEXT, reason TEXT,
                     duration TEXT, status TEXT DEFAULT 'open',
                     claimed_by TEXT, claimed_at TIMESTAMPTZ,
                     donated_to TEXT, donated_at TIMESTAMPTZ,
                     from_mod_id TEXT,
                     channel_id TEXT, message_id TEXT,
                     created_at TIMESTAMPTZ DEFAULT now())
    mod_tracks      (guild_id TEXT, mod_id TEXT, modded INT DEFAULT 0,
                     claimed INT DEFAULT 0, donated INT DEFAULT 0,
                     received_donation INT DEFAULT 0,
                     PRIMARY KEY (guild_id, mod_id))
    """

    def __init__(self, url: str, anon_key: str):
        # Strip trailing slash
        self.url     = url.rstrip("/")
        self.key     = anon_key
        self._session: aiohttp.ClientSession | None = None

    # ── Session management ────────────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Low-level REST helpers ────────────────────────────────

    def _rest(self, table: str) -> str:
        return f"{self.url}/rest/v1/{table}"

    async def _get(self, table: str, params: dict | None = None) -> list[dict]:
        session = await self._get_session()
        async with session.get(
            self._rest(table),
            headers=_headers(self.key),
            params=params or {},
        ) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(f"Supabase GET {table} {resp.status}: {text}")
            return json.loads(text) if text else []

    async def _post(self, table: str, data: dict) -> list[dict]:
        session = await self._get_session()
        async with session.post(
            self._rest(table),
            headers=_headers(self.key),
            json=data,
        ) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(f"Supabase POST {table} {resp.status}: {text}")
            return json.loads(text) if text else []

    async def _patch(self, table: str, match: dict, data: dict) -> list[dict]:
        session = await self._get_session()
        params = {k: f"eq.{v}" for k, v in match.items()}
        async with session.patch(
            self._rest(table),
            headers=_headers(self.key),
            params=params,
            json=data,
        ) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(f"Supabase PATCH {table} {resp.status}: {text}")
            return json.loads(text) if text else []

    async def _delete(self, table: str, match: dict) -> list[dict]:
        session = await self._get_session()
        params = {k: f"eq.{v}" for k, v in match.items()}
        async with session.delete(
            self._rest(table),
            headers=_headers(self.key),
            params=params,
        ) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(f"Supabase DELETE {table} {resp.status}: {text}")
            return json.loads(text) if text else []

    async def _upsert(self, table: str, data: dict, on_conflict: str) -> list[dict]:
        session = await self._get_session()
        headers = {**_headers(self.key), "Prefer": f"resolution=merge-duplicates,return=representation"}
        async with session.post(
            self._rest(table),
            headers=headers,
            params={"on_conflict": on_conflict},
            json=data,
        ) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(f"Supabase UPSERT {table} {resp.status}: {text}")
            return json.loads(text) if text else []

    # ── Type-coercion helpers (matches old SDK behaviour) ─────

    @staticmethod
    def _bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes")
        return bool(value)

    @staticmethod
    def _int(value: Any, default: int = 0) -> int:
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    # ══════════════════════════════════════════════════════════
    # Guild config
    # ══════════════════════════════════════════════════════════

    async def get_config(self, guild_id: int) -> dict:
        """Return the JSONB config dict for a guild (empty dict if not found)."""
        rows = await self._get("guild_configs", {"guild_id": f"eq.{guild_id}", "select": "config"})
        if rows:
            return rows[0].get("config") or {}
        return {}

    async def set_config(self, guild_id: int, key: str, value: Any) -> None:
        """Set a single key in a guild's config JSONB."""
        config = await self.get_config(guild_id)
        config[key] = value
        await self._upsert("guild_configs", {"guild_id": str(guild_id), "config": config}, "guild_id")

    async def set_full_config(self, guild_id: int, config: dict) -> None:
        """Replace the entire config dict for a guild."""
        await self._upsert("guild_configs", {"guild_id": str(guild_id), "config": config}, "guild_id")

    # ══════════════════════════════════════════════════════════
    # Mod logs
    # ══════════════════════════════════════════════════════════

    async def add_log(self, guild_id: int, action: str, mod_id: int,
                      target_id: int, reason: str) -> None:
        await self._post("mod_logs", {
            "guild_id":  str(guild_id),
            "action":    action,
            "mod_id":    str(mod_id),
            "target_id": str(target_id),
            "reason":    reason,
        })

    async def get_logs(self, guild_id: int, limit: int = 10) -> list[dict]:
        rows = await self._get("mod_logs", {
            "guild_id": f"eq.{guild_id}",
            "order":    "created_at.desc",
            "limit":    str(limit),
        })
        return rows

    async def clear_logs(self, guild_id: int) -> None:
        await self._delete("mod_logs", {"guild_id": str(guild_id)})

    # ══════════════════════════════════════════════════════════
    # Warnings
    # ══════════════════════════════════════════════════════════

    async def add_warning(self, guild_id: int, user_id: int,
                          mod_id: int, reason: str) -> None:
        await self._post("warnings", {
            "guild_id": str(guild_id),
            "user_id":  str(user_id),
            "mod_id":   str(mod_id),
            "reason":   reason,
        })

    async def get_warnings(self, guild_id: int, user_id: int) -> list[dict]:
        return await self._get("warnings", {
            "guild_id": f"eq.{guild_id}",
            "user_id":  f"eq.{user_id}",
            "order":    "created_at.asc",
        })

    async def clear_warnings(self, guild_id: int, user_id: int) -> None:
        session = await self._get_session()
        async with session.delete(
            self._rest("warnings"),
            headers=_headers(self.key),
            params={"guild_id": f"eq.{guild_id}", "user_id": f"eq.{user_id}"},
        ) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"clear_warnings {resp.status}: {await resp.text()}")

    async def remove_warning(self, warning_id: int) -> None:
        await self._delete("warnings", {"id": str(warning_id)})

    async def get_warn_thresholds(self, guild_id: int) -> dict:
        config = await self.get_config(guild_id)
        return {
            "mute_at":    self._int(config.get("warn_mute_at"),    3),
            "kick_at":    self._int(config.get("warn_kick_at"),    5),
            "ban_at":     self._int(config.get("warn_ban_at"),     10),
            "mute_hours": float(config.get("warn_mute_hours") or 1.0),
        }

    # ══════════════════════════════════════════════════════════
    # Bad words (auto-mod)
    # ══════════════════════════════════════════════════════════

    async def get_bad_words(self, guild_id: int) -> list[str]:
        rows = await self._get("bad_words", {"guild_id": f"eq.{guild_id}", "select": "word"})
        return [r["word"] for r in rows]

    async def add_bad_word(self, guild_id: int, word: str) -> None:
        await self._upsert("bad_words", {"guild_id": str(guild_id), "word": word}, "guild_id,word")

    async def remove_bad_word(self, guild_id: int, word: str) -> None:
        session = await self._get_session()
        async with session.delete(
            self._rest("bad_words"),
            headers=_headers(self.key),
            params={"guild_id": f"eq.{guild_id}", "word": f"eq.{word}"},
        ) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"remove_bad_word {resp.status}: {await resp.text()}")

    # ══════════════════════════════════════════════════════════
    # Self-assignable roles
    # ══════════════════════════════════════════════════════════

    async def get_self_roles(self, guild_id: int) -> list[str]:
        rows = await self._get("self_roles", {"guild_id": f"eq.{guild_id}", "select": "role_id"})
        return [r["role_id"] for r in rows]

    async def add_self_role(self, guild_id: int, role_id: str) -> None:
        await self._upsert("self_roles", {"guild_id": str(guild_id), "role_id": role_id}, "guild_id,role_id")

    async def remove_self_role(self, guild_id: int, role_id: str) -> None:
        session = await self._get_session()
        async with session.delete(
            self._rest("self_roles"),
            headers=_headers(self.key),
            params={"guild_id": f"eq.{guild_id}", "role_id": f"eq.{role_id}"},
        ) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"remove_self_role {resp.status}: {await resp.text()}")

    # ══════════════════════════════════════════════════════════
    # Shared moderation
    # ══════════════════════════════════════════════════════════

    async def create_shared_mod(self, guild_id: int, mod_id: int, target_id: int,
                                 action: str, reason: str, duration: str | None = None) -> dict:
        rows = await self._post("shared_mods", {
            "guild_id":  str(guild_id),
            "mod_id":    str(mod_id),
            "target_id": str(target_id),
            "action":    action,
            "reason":    reason,
            "duration":  duration,
            "status":    "open",
        })
        return rows[0] if rows else {}

    async def get_shared_mod(self, mod_id: int) -> dict | None:
        rows = await self._get("shared_mods", {"id": f"eq.{mod_id}"})
        return rows[0] if rows else None

    async def get_shared_mod_by_message(self, message_id: str) -> dict | None:
        rows = await self._get("shared_mods", {"message_id": f"eq.{message_id}"})
        return rows[0] if rows else None

    async def update_shared_mod_message(self, mod_id: int, channel_id: int, message_id: int) -> None:
        await self._patch("shared_mods", {"id": str(mod_id)}, {
            "channel_id": str(channel_id),
            "message_id": str(message_id),
        })

    async def claim_shared_mod(self, mod_id: int, claimer_id: int) -> None:
        from datetime import datetime, timezone
        await self._patch("shared_mods", {"id": str(mod_id)}, {
            "status":     "claimed",
            "claimed_by": str(claimer_id),
            "claimed_at": datetime.now(timezone.utc).isoformat(),
        })

    async def donate_shared_mod(self, mod_id: int, donor_id: int, recipient_id: int) -> None:
        from datetime import datetime, timezone
        await self._patch("shared_mods", {"id": str(mod_id)}, {
            "status":      "donated",
            "donated_to":  str(recipient_id),
            "from_mod_id": str(donor_id),
            "donated_at":  datetime.now(timezone.utc).isoformat(),
        })

    async def list_shared_mods(self, guild_id: int, status: str | None = None) -> list[dict]:
        params: dict = {"guild_id": f"eq.{guild_id}", "order": "created_at.desc", "limit": "50"}
        if status:
            params["status"] = f"eq.{status}"
        return await self._get("shared_mods", params)

    # ══════════════════════════════════════════════════════════
    # Mod tracking
    # ══════════════════════════════════════════════════════════

    async def get_modtrack(self, guild_id: int, mod_id: int) -> dict:
        rows = await self._get("mod_tracks", {
            "guild_id": f"eq.{guild_id}",
            "mod_id":   f"eq.{mod_id}",
        })
        return rows[0] if rows else {}

    async def update_modtrack(self, guild_id: int, mod_id: int, field: str) -> None:
        """Increment a modtrack counter field by 1 (upserts the row if missing)."""
        valid_fields = {"modded", "claimed", "donated", "received_donation"}
        if field not in valid_fields:
            return

        # Get current row
        rows = await self._get("mod_tracks", {
            "guild_id": f"eq.{guild_id}",
            "mod_id":   f"eq.{mod_id}",
        })
        if rows:
            current = rows[0].get(field, 0) or 0
            await self._patch("mod_tracks", {
                "guild_id": str(guild_id),
                "mod_id":   str(mod_id),
            }, {field: current + 1})
        else:
            await self._upsert("mod_tracks", {
                "guild_id":           str(guild_id),
                "mod_id":             str(mod_id),
                "modded":             1 if field == "modded" else 0,
                "claimed":            1 if field == "claimed" else 0,
                "donated":            1 if field == "donated" else 0,
                "received_donation":  1 if field == "received_donation" else 0,
            }, "guild_id,mod_id")

    async def get_received_donations(self, guild_id: int, mod_id: int) -> list[dict]:
        """Return shared_mods rows where this user was the donation recipient."""
        return await self._get("shared_mods", {
            "guild_id":   f"eq.{guild_id}",
            "donated_to": f"eq.{mod_id}",
            "order":      "donated_at.desc",
            "limit":      "20",
        })
