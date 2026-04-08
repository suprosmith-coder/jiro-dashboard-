"""
main.py — 07Dipper / Jiro Discord Bot
NixAI • by Blueey

Run with: python main.py
"""

import os
import asyncio
import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv

# ── Load environment variables ─────────────────────────────
load_dotenv()

BOT_TOKEN    = os.getenv("BOT_TOKEN")
GROQ_KEY     = os.getenv("GROQ_KEY")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
PREFIX       = os.getenv("PREFIX", "?")

missing = []
if not BOT_TOKEN: missing.append("BOT_TOKEN")
if not SUPABASE_URL or not SUPABASE_KEY: missing.append("SUPABASE_URL/SUPABASE_KEY")
if not GROQ_KEY: missing.append("GROQ_KEY")
if missing:
    raise ValueError(f"Missing required environment variable(s): {', '.join(missing)}")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

class Jiro(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or(PREFIX, "!"),
            intents=intents,
            help_command=None,
            case_insensitive=True,
        )
        self.groq_key   = GROQ_KEY
        self.groq_model = GROQ_MODEL
        self._session: aiohttp.ClientSession | None = None

        from database import Database
        self.db = Database(url=SUPABASE_URL, anon_key=SUPABASE_KEY)

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def ask_groq(self, prompt: str, *, system: str = None, model: str = None) -> str:
        model   = model or self.groq_model
        session = await self.get_session()
        messages = [{"role": "system", "content": system}] if system else []
        messages.append({"role": "user", "content": prompt})
        try:
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.groq_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages, "max_tokens": 1024, "temperature": 0.7},
                timeout=aiohttp.ClientTimeout(total=25),
            ) as resp:
                if resp.status != 200:
                    return f"[Groq error {resp.status}: {(await resp.text())[:200]}]"
                data = await resp.json()
                return data["choices"][0]["message"]["content"].strip()
        except asyncio.TimeoutError:
            return "[Groq timed out — try again]"
        except Exception as e:
            return f"[Groq error: {e}]"

    async def setup_hook(self):
        cog_order = [
            "cogs.error_handler",
            "cogs.automod",
            "cogs.help",
            "cogs.logs",
            "cogs.moderation",
            "cogs.roles",
            "cogs.shared_moderation",
            "cogs.warnings",
            "cogs.welcome",
            "cogs.fun",
            "cogs.ai",
            "cogs.games",
            "cogs.chats",
        ]
        for cog in cog_order:
            try:
                await self.load_extension(cog)
                print(f"[OK] Loaded {cog}")
            except Exception as e:
                print(f"[ERR] Failed to load {cog}: {e}")
        try:
            synced = await self.tree.sync()
            print(f"[OK] Synced {len(synced)} slash commands globally")
        except Exception as e:
            print(f"[ERR] Slash command sync failed: {e}")

    async def on_ready(self):
        print(f"\n{'='*40}")
        print(f"  Jiro is online as {self.user} ({self.user.id})")
        print(f"  Guilds: {len(self.guilds)}  |  Prefix: {PREFIX}  |  Model: {self.groq_model}")
        print(f"{'='*40}\n")
        await self.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching, name=f"{PREFIX}help | NixAI"))

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if self.user in message.mentions and message.guild:
            content = message.content.replace(f"<@{self.user.id}>", "").replace(f"<@!{self.user.id}>", "").strip()
            if content:
                try:
                    config = await self.db.get_config(message.guild.id)
                    if self.db._bool(config.get("ai_enabled"), default=True):
                        async with message.channel.typing():
                            from cogs.ai import get_system_prompt
                            system = await get_system_prompt(self, message.guild.id)
                            model  = config.get("ai_model") or self.groq_model
                            reply  = await self.ask_groq(content, system=system, model=model)
                        await message.reply(reply[:2000])
                except Exception as e:
                    print(f"[ERR] Mention reply failed: {e}")
        await self.process_commands(message)

    async def close(self):
        await self.db.close()
        if self._session and not self._session.closed:
            await self._session.close()
        await super().close()

async def main():
    bot = Jiro()
    async with bot:
        await bot.start(BOT_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
