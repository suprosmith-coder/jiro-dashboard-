import discord
from discord.ext import commands
from discord import app_commands
from utils.embeds import embed
from utils.config import icon, safe_defer, safe_send
import logging

log = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = (
    "You are Jiro, a powerful and witty Discord bot assistant created by Blueey, "
    "the founder of NixAI. You are NixAI's flagship Discord bot — the AI platform "
    "behind CyanixAI. Here is what you are capable of:\n\n"

    "MODERATION: You can kick, ban, unban, mute (with flexible durations like 10s/10m/12h/7d), "
    "unmute, purge messages (including old ones safely), and set slowmode.\n\n"

    "SHARED MODERATION: Moderators can share a moderation action with other mods using !sharemod. "
    "Other mods can Claim it, Donate it to someone else, or Leave it Open. "
    "Use !modtrack to see how many mods you've done, claimed, donated, or received.\n\n"

    "WARNINGS: Warn members with !warn. Warnings auto-escalate based on configurable thresholds. "
    "Use !warnings, !clearwarnings, !delwarning to manage them. Use !warnconfig to adjust thresholds.\n\n"

    "AUTO-MOD: Automatically punishes spam, Discord invite links, external URLs, and banned words. "
    "Toggle features with !automod. Configure spam sensitivity with !automod spamconfig.\n\n"

    "LOGS: Log all mod actions to a channel with !setlogchannel. View recent logs with !modlogs. "
    "Automatically logs message edits, deletions, member joins and leaves.\n\n"

    "WELCOME: Set a welcome channel and message with {user}, {server}, {count} placeholders. "
    "Also supports auto-roles on member join via !setautorole. Toggle with !togglewelcome.\n\n"

    "ROLES: Add/remove roles, set auto-roles, create self-assignable roles with !iam/!iamnot.\n\n"

    "FUN: Jokes, polls, magic 8-ball, coinflip, dice rolls, random numbers, ship, trivia, mock text.\n\n"

    "GAMES: Truth or Dare (/todlaunch, /stod, /tod), Never Have I Ever (/nr).\n\n"

    "AI: You can answer questions (!ask), summarize text (!summarize), roast members (!roast), "
    "translate text (!translate), compliment members (!compliment), explain topics (!explain), "
    "and argue a debate side (!debate). You respond when mentioned directly in chat too.\n\n"

    "Keep answers concise and Discord-friendly. No huge markdown walls. "
    "When roasting, keep it playful — never genuinely hurtful. "
    "You are proud to be made by Blueey and powered by NixAI / CyanixAI."
)

# ── Fallback reply when the AI is unavailable ─────────────────────────────────
_AI_FALLBACK = (
    "I couldn't reach my AI backend right now. "
    "Please try again in a moment, or check that the Groq API key is set correctly."
)


async def get_system_prompt(bot, guild_id: int) -> str:
    """Return the guild's custom system prompt or the default."""
    try:
        config = await bot.db.get_config(guild_id)
        custom = config.get("ai_custom_prompt")
        return custom.strip() if custom and custom.strip() else DEFAULT_SYSTEM_PROMPT
    except Exception as exc:
        log.warning(f"[AI] Failed to fetch system prompt for guild {guild_id}: {exc}")
        return DEFAULT_SYSTEM_PROMPT


class AI(commands.Cog):
    """Groq-powered AI commands."""

    def __init__(self, bot):
        self.bot = bot

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _ai_enabled(self, guild_id: int) -> bool:
        try:
            config = await self.bot.db.get_config(guild_id)
            return self.bot.db._bool(config.get("ai_enabled"), default=True)
        except Exception as exc:
            log.warning(f"[AI] _ai_enabled check failed for guild {guild_id}: {exc}")
            return True  # Fail open — don't block users if DB hiccups

    async def _ai_reply(self, guild_id: int, prompt: str) -> str:
        """
        Call Groq and return the response string.
        Returns a friendly fallback message instead of raising on any failure.
        """
        try:
            system = await get_system_prompt(self.bot, guild_id)
            config = await self.bot.db.get_config(guild_id)
            model  = config.get("ai_model") or self.bot.groq_model
            result = await self.bot.ask_groq(prompt, system=system, model=model)
            if not result or not result.strip():
                return _AI_FALLBACK
            return result
        except Exception as exc:
            log.error(f"[AI] _ai_reply failed for guild {guild_id}: {type(exc).__name__}: {exc}")
            return _AI_FALLBACK

    def _disabled_embed(self) -> discord.Embed:
        return embed(
            f"{icon('ai')} AI Disabled",
            f"AI commands are turned off for this server.\n"
            f"An admin can re-enable them with `?aion`.",
            color="warn")

    def _error_embed(self, title: str = "AI Error") -> discord.Embed:
        return embed(
            f"{icon('error')} {title}",
            _AI_FALLBACK,
            color="error")

    # ── Ask ───────────────────────────────────────────────────────────────────

    @commands.command(name="ask")
    async def ask_prefix(self, ctx: commands.Context, *, question: str):
        """Ask Jiro a question. ?ask <question>"""
        if not await self._ai_enabled(ctx.guild.id):
            return await ctx.send(embed=self._disabled_embed())
        async with ctx.typing():
            reply = await self._ai_reply(ctx.guild.id, question)
        e = embed(f"{icon('ai')} Jiro", color="info")
        e.add_field(name="Question", value=question[:1000], inline=False)
        e.add_field(name="Answer",   value=reply[:1000],   inline=False)
        await ctx.send(embed=e)

    @app_commands.command(name="ask", description="Ask Jiro a question")
    async def ask_slash(self, interaction: discord.Interaction, question: str):
        if not await self._ai_enabled(interaction.guild.id):
            return await safe_send(interaction, embed=self._disabled_embed(), ephemeral=True)
        if not await safe_defer(interaction):
            return
        reply = await self._ai_reply(interaction.guild.id, question)
        e = embed(f"{icon('ai')} Jiro", color="info")
        e.add_field(name="Question", value=question[:1000], inline=False)
        e.add_field(name="Answer",   value=reply[:1000],   inline=False)
        await interaction.followup.send(embed=e)

    # ── Summarize ─────────────────────────────────────────────────────────────

    @commands.command(name="summarize", aliases=["tldr"])
    async def summarize_prefix(self, ctx: commands.Context, *, text: str):
        """Summarize a block of text. ?summarize <text>"""
        if not await self._ai_enabled(ctx.guild.id):
            return await ctx.send(embed=self._disabled_embed())
        async with ctx.typing():
            reply = await self._ai_reply(
                ctx.guild.id,
                f"Summarize the following in 2-3 sentences:\n\n{text}")
        await ctx.send(embed=embed(f"{icon('summary')} Summary", reply[:1500], color="info"))

    @app_commands.command(name="summarize", description="Summarize a block of text")
    async def summarize_slash(self, interaction: discord.Interaction, text: str):
        if not await self._ai_enabled(interaction.guild.id):
            return await safe_send(interaction, embed=self._disabled_embed(), ephemeral=True)
        if not await safe_defer(interaction):
            return
        reply = await self._ai_reply(
            interaction.guild.id,
            f"Summarize the following in 2-3 sentences:\n\n{text}")
        await interaction.followup.send(
            embed=embed(f"{icon('summary')} Summary", reply[:1500], color="info"))

    # ── Roast ─────────────────────────────────────────────────────────────────

    @commands.command(name="roast")
    async def roast_prefix(self, ctx: commands.Context, member: discord.Member):
        """Have Jiro roast a member. ?roast @user"""
        if not await self._ai_enabled(ctx.guild.id):
            return await ctx.send(embed=self._disabled_embed())
        async with ctx.typing():
            prompt = (
                f'Give a short, playful, funny roast for a Discord user named '
                f'"{member.display_name}". Keep it light-hearted and not genuinely hurtful.'
            )
            reply = await self._ai_reply(ctx.guild.id, prompt)
        await ctx.send(embed=embed(
            f"{icon('roast')} Roasting {member.display_name}", reply[:1000], color="warn"))

    @app_commands.command(name="roast", description="Have Jiro roast a member")
    async def roast_slash(self, interaction: discord.Interaction, member: discord.Member):
        if not await self._ai_enabled(interaction.guild.id):
            return await safe_send(interaction, embed=self._disabled_embed(), ephemeral=True)
        if not await safe_defer(interaction):
            return
        prompt = (
            f'Give a short, playful, funny roast for a Discord user named '
            f'"{member.display_name}". Keep it light-hearted and not genuinely hurtful.'
        )
        reply = await self._ai_reply(interaction.guild.id, prompt)
        await interaction.followup.send(embed=embed(
            f"{icon('roast')} Roasting {member.display_name}", reply[:1000], color="warn"))

    # ── Translate ─────────────────────────────────────────────────────────────

    @commands.command(name="translate")
    async def translate_prefix(self, ctx: commands.Context, language: str, *, text: str):
        """Translate text. ?translate <language> <text>"""
        if not await self._ai_enabled(ctx.guild.id):
            return await ctx.send(embed=self._disabled_embed())
        async with ctx.typing():
            prompt = f'Translate the following text to {language}. Return only the translation:\n\n{text}'
            reply = await self._ai_reply(ctx.guild.id, prompt)
        e = embed(f"{icon('translate')} Translation → {language}", color="info")
        e.add_field(name="Original",    value=text[:500],  inline=False)
        e.add_field(name="Translation", value=reply[:500], inline=False)
        await ctx.send(embed=e)

    @app_commands.command(name="translate", description="Translate text to any language")
    async def translate_slash(self, interaction: discord.Interaction, language: str, text: str):
        if not await self._ai_enabled(interaction.guild.id):
            return await safe_send(interaction, embed=self._disabled_embed(), ephemeral=True)
        if not await safe_defer(interaction):
            return
        prompt = f'Translate the following text to {language}. Return only the translation:\n\n{text}'
        reply  = await self._ai_reply(interaction.guild.id, prompt)
        e = embed(f"{icon('translate')} Translation → {language}", color="info")
        e.add_field(name="Original",    value=text[:500],  inline=False)
        e.add_field(name="Translation", value=reply[:500], inline=False)
        await interaction.followup.send(embed=e)

    # ── Compliment ────────────────────────────────────────────────────────────

    @commands.command(name="compliment")
    async def compliment_prefix(self, ctx: commands.Context, member: discord.Member):
        """Give a member a compliment. ?compliment @user"""
        if not await self._ai_enabled(ctx.guild.id):
            return await ctx.send(embed=self._disabled_embed())
        async with ctx.typing():
            prompt = (
                f'Give a heartfelt, genuine compliment to a Discord user named '
                f'"{member.display_name}". Keep it short and wholesome.'
            )
            reply = await self._ai_reply(ctx.guild.id, prompt)
        await ctx.send(embed=embed(
            f"{icon('compliment')} For {member.display_name} 💙", reply[:1000], color="success"))

    @app_commands.command(name="compliment", description="Give a member a heartfelt compliment")
    async def compliment_slash(self, interaction: discord.Interaction, member: discord.Member):
        if not await self._ai_enabled(interaction.guild.id):
            return await safe_send(interaction, embed=self._disabled_embed(), ephemeral=True)
        if not await safe_defer(interaction):
            return
        prompt = (
            f'Give a heartfelt, genuine compliment to a Discord user named '
            f'"{member.display_name}". Keep it short and wholesome.'
        )
        reply = await self._ai_reply(interaction.guild.id, prompt)
        await interaction.followup.send(embed=embed(
            f"{icon('compliment')} For {member.display_name} 💙", reply[:1000], color="success"))

    # ── Explain ───────────────────────────────────────────────────────────────

    @commands.command(name="explain")
    async def explain_prefix(self, ctx: commands.Context, *, topic: str):
        """Get a simple explanation of any topic. ?explain <topic>"""
        if not await self._ai_enabled(ctx.guild.id):
            return await ctx.send(embed=self._disabled_embed())
        async with ctx.typing():
            prompt = (
                f"Explain '{topic}' in simple terms, as if explaining to someone new. "
                f"Keep it concise and Discord-friendly."
            )
            reply = await self._ai_reply(ctx.guild.id, prompt)
        e = embed(f"{icon('explain')} Explain: {topic[:100]}", color="info")
        e.description = reply[:1500]
        await ctx.send(embed=e)

    @app_commands.command(name="explain", description="Get a simple explanation of any topic")
    async def explain_slash(self, interaction: discord.Interaction, topic: str):
        if not await self._ai_enabled(interaction.guild.id):
            return await safe_send(interaction, embed=self._disabled_embed(), ephemeral=True)
        if not await safe_defer(interaction):
            return
        prompt = (
            f"Explain '{topic}' in simple terms, as if explaining to someone new. "
            f"Keep it concise and Discord-friendly."
        )
        reply = await self._ai_reply(interaction.guild.id, prompt)
        e = embed(f"{icon('explain')} Explain: {topic[:100]}", color="info")
        e.description = reply[:1500]
        await interaction.followup.send(embed=e)

    # ── Debate ────────────────────────────────────────────────────────────────

    @commands.command(name="debate")
    async def debate_prefix(self, ctx: commands.Context, side: str, *, topic: str):
        """Argue a side of a debate. ?debate <for|against> <topic>"""
        if not await self._ai_enabled(ctx.guild.id):
            return await ctx.send(embed=self._disabled_embed())
        side_lower = side.lower()
        if side_lower not in ("for", "against"):
            return await ctx.send(embed=embed(
                f"{icon('error')} Invalid Side",
                "Side must be `for` or `against`.\n**Usage:** `?debate <for|against> <topic>`",
                color="error"))
        async with ctx.typing():
            prompt = (
                f"Argue {side_lower} the following topic in 3-4 punchy bullet points "
                f"suitable for Discord: {topic}"
            )
            reply = await self._ai_reply(ctx.guild.id, prompt)
        side_icon = icon("debate_for") if side_lower == "for" else icon("debate_against")
        await ctx.send(embed=embed(
            f"{side_icon} Debate ({side_lower.capitalize()}): {topic[:100]}", reply[:1500], color="info"))

    @app_commands.command(name="debate", description="Argue for or against a topic")
    async def debate_slash(self, interaction: discord.Interaction, side: str, topic: str):
        if not await self._ai_enabled(interaction.guild.id):
            return await safe_send(interaction, embed=self._disabled_embed(), ephemeral=True)
        side_lower = side.lower()
        if side_lower not in ("for", "against"):
            return await safe_send(interaction, embed=embed(
                f"{icon('error')} Side must be `for` or `against`.", color="error"), ephemeral=True)
        if not await safe_defer(interaction):
            return
        prompt = (
            f"Argue {side_lower} the following topic in 3-4 punchy bullet points "
            f"suitable for Discord: {topic}"
        )
        reply = await self._ai_reply(interaction.guild.id, prompt)
        side_icon = icon("debate_for") if side_lower == "for" else icon("debate_against")
        await interaction.followup.send(embed=embed(
            f"{side_icon} Debate ({side_lower.capitalize()}): {topic[:100]}", reply[:1500], color="info"))

    # ── AI Toggle ─────────────────────────────────────────────────────────────

    @commands.command(name="aion")
    @commands.has_permissions(administrator=True)
    async def aion(self, ctx: commands.Context):
        """Enable AI for this server. ?aion"""
        try:
            await self.bot.db.set_config(ctx.guild.id, "ai_enabled", True)
            await ctx.send(embed=embed(
                f"{icon('ok')} AI Enabled",
                "Jiro's AI commands are now active in this server.", color="success"))
        except Exception as exc:
            log.error(f"[AI] aion DB error: {exc}")
            await ctx.send(embed=embed(
                f"{icon('error')} Database Error",
                "Could not update AI setting. Please try again.", color="error"))

    @commands.command(name="aioff")
    @commands.has_permissions(administrator=True)
    async def aioff(self, ctx: commands.Context):
        """Disable AI for this server. ?aioff"""
        try:
            await self.bot.db.set_config(ctx.guild.id, "ai_enabled", False)
            await ctx.send(embed=embed(
                f"{icon('error')} AI Disabled",
                "Jiro's AI commands have been disabled in this server.\n"
                "Use `?aion` to re-enable them.", color="warn"))
        except Exception as exc:
            log.error(f"[AI] aioff DB error: {exc}")
            await ctx.send(embed=embed(
                f"{icon('error')} Database Error",
                "Could not update AI setting. Please try again.", color="error"))

    # ── Set model ─────────────────────────────────────────────────────────────

    @commands.command(name="setmodel")
    @commands.has_permissions(administrator=True)
    async def setmodel(self, ctx: commands.Context, *, model_id: str):
        """Set the Groq model for this server.
        Common models: llama-3.3-70b-versatile, mixtral-8x7b-32768, llama3-8b-8192"""
        try:
            await self.bot.db.set_config(ctx.guild.id, "ai_model", model_id.strip())
            e = embed(f"{icon('model')} AI Model Updated", color="success")
            e.add_field(name="New Model", value=f"`{model_id.strip()}`", inline=False)
            e.set_footer(text="Make sure this model is available on your Groq account.")
            await ctx.send(embed=e)
        except Exception as exc:
            log.error(f"[AI] setmodel DB error: {exc}")
            await ctx.send(embed=embed(
                f"{icon('error')} Database Error",
                "Could not save the model. Please try again.", color="error"))

    @app_commands.command(name="setmodel", description="Set the Groq AI model for this server (Admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def setmodel_slash(self, interaction: discord.Interaction, model_id: str):
        try:
            await self.bot.db.set_config(interaction.guild.id, "ai_model", model_id.strip())
            e = embed(f"{icon('model')} AI Model Updated", color="success")
            e.add_field(name="New Model", value=f"`{model_id.strip()}`", inline=False)
            e.set_footer(text="Make sure this model is available on your Groq account.")
            await interaction.response.send_message(embed=e)
        except Exception as exc:
            log.error(f"[AI] setmodel_slash error: {exc}")
            await safe_send(interaction, embed=embed(
                f"{icon('error')} Database Error",
                "Could not save the model. Please try again.", color="error"), ephemeral=True)

    # ── Set custom system prompt ───────────────────────────────────────────────

    @commands.command(name="setprompt")
    @commands.has_permissions(administrator=True)
    async def setprompt(self, ctx: commands.Context, *, prompt: str):
        """Set a custom AI system prompt for this server. ?setprompt <prompt>"""
        if len(prompt) > 2000:
            return await ctx.send(embed=embed(
                f"{icon('error')} Prompt Too Long",
                "The system prompt must be under 2000 characters.", color="error"))
        try:
            await self.bot.db.set_config(ctx.guild.id, "ai_custom_prompt", prompt)
            e = embed(f"{icon('ok')} Custom Prompt Set", color="success")
            e.add_field(name="Preview",
                        value=prompt[:500] + ("…" if len(prompt) > 500 else ""),
                        inline=False)
            await ctx.send(embed=e)
        except Exception as exc:
            log.error(f"[AI] setprompt DB error: {exc}")
            await ctx.send(embed=embed(
                f"{icon('error')} Database Error",
                "Could not save the prompt. Please try again.", color="error"))

    @commands.command(name="clearprompt")
    @commands.has_permissions(administrator=True)
    async def clearprompt(self, ctx: commands.Context):
        """Reset the AI system prompt back to the Jiro default. ?clearprompt"""
        try:
            await self.bot.db.set_config(ctx.guild.id, "ai_custom_prompt", None)
            await ctx.send(embed=embed(
                f"{icon('ok')} Prompt Reset",
                "The AI will now use the default Jiro system prompt.", color="success"))
        except Exception as exc:
            log.error(f"[AI] clearprompt DB error: {exc}")
            await ctx.send(embed=embed(
                f"{icon('error')} Database Error",
                "Could not reset the prompt. Please try again.", color="error"))

    # ── Model info ─────────────────────────────────────────────────────────────

    @commands.command(name="aimodel")
    async def aimodel_prefix(self, ctx: commands.Context):
        """Show the current AI model and status for this server. ?aimodel"""
        try:
            config  = await self.bot.db.get_config(ctx.guild.id)
            model   = config.get("ai_model") or self.bot.groq_model
            enabled = self.bot.db._bool(config.get("ai_enabled"), True)
            custom  = bool(config.get("ai_custom_prompt"))
        except Exception as exc:
            log.warning(f"[AI] aimodel DB error: {exc}")
            model, enabled, custom = self.bot.groq_model, True, False

        key_set = f"{icon('ok')} Set" if getattr(self.bot, "groq_key", None) else f"{icon('error')} Not set"

        e = embed(f"{icon('model')} AI Model Info", color="info")
        e.add_field(name="Provider",       value="Groq",                                    inline=True)
        e.add_field(name="Model",          value=f"`{model}`",                              inline=True)
        e.add_field(name="API Key",        value=key_set,                                   inline=True)
        e.add_field(name="Enabled",        value=icon("ok") if enabled else icon("error"),  inline=True)
        e.add_field(name="Custom Prompt",  value="Yes" if custom else "No (default)",       inline=True)
        e.set_footer(text="Use ?setmodel to change the model | ?aion/?aioff to toggle")
        await ctx.send(embed=e)


async def setup(bot):
    await bot.add_cog(AI(bot))
