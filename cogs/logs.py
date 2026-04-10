import discord
from discord.ext import commands
from discord import app_commands
from utils.embeds import embed
from utils.config import icon


class Logs(commands.Cog):
    """Audit log management and event logging."""

    def __init__(self, bot):
        self.bot = bot

    # ── Set log channel ────────────────────────────────────────
    @commands.command(name="setlogchannel")
    @commands.has_permissions(administrator=True)
    async def set_log_channel_prefix(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        await self.bot.db.set_config(ctx.guild.id, "log_channel_id", channel.id)
        await ctx.send(embed=embed(f"{icon('ok')} Log channel set to {channel.mention}", color="success"))

    @app_commands.command(name="setlogchannel", description="Set the mod-log channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_log_channel_slash(self, interaction: discord.Interaction,
                                    channel: discord.TextChannel = None):
        channel = channel or interaction.channel
        await self.bot.db.set_config(interaction.guild.id, "log_channel_id", channel.id)
        await interaction.response.send_message(
            embed=embed(f"{icon('ok')} Log channel set to {channel.mention}", color="success"))

    # ── View recent logs ───────────────────────────────────────
    @commands.command(name="modlogs")
    @commands.has_permissions(manage_messages=True)
    async def modlogs_prefix(self, ctx, limit: int = 10):
        logs = await self.bot.db.get_logs(ctx.guild.id, limit=limit)
        if not logs:
            return await ctx.send(embed=embed("No mod logs found.", color="info"))
        e = embed(f"{icon('log')} Recent Mod Logs (last {len(logs)})", color="log")
        for log in logs:
            mod    = ctx.guild.get_member(int(log["mod_id"]))
            target = ctx.guild.get_member(int(log["target_id"]))
            e.add_field(
                name=f"[{log['created_at'][:10]}] {log['action']}",
                value=(f"**Mod:** {mod.mention if mod else log['mod_id']} "
                       f"→ **Target:** {target.mention if target else log['target_id']}\n"
                       f"**Reason:** {log['reason']}"),
                inline=False,
            )
        await ctx.send(embed=e)

    @app_commands.command(name="modlogs", description="View recent mod actions")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def modlogs_slash(self, interaction: discord.Interaction, limit: int = 10):
        logs = await self.bot.db.get_logs(interaction.guild.id, limit=limit)
        if not logs:
            return await interaction.response.send_message(embed=embed("No mod logs found.", color="info"))
        e = embed(f"{icon('log')} Recent Mod Logs (last {len(logs)})", color="log")
        for log in logs:
            e.add_field(
                name=f"[{log['created_at'][:10]}] {log['action']}",
                value=f"Mod: `{log['mod_id']}` → Target: `{log['target_id']}`\nReason: {log['reason']}",
                inline=False,
            )
        await interaction.response.send_message(embed=e)

    # ── Clear logs ─────────────────────────────────────────────
    @commands.command(name="clearlogs")
    @commands.has_permissions(administrator=True)
    async def clearlogs_prefix(self, ctx):
        """Clear all stored mod logs for this server. Admin only."""
        await self.bot.db.clear_logs(ctx.guild.id)
        await ctx.send(embed=embed(f"{icon('ok')} All mod logs cleared for this server.", color="success"))

    @app_commands.command(name="clearlogs", description="Clear all mod logs for this server (Admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def clearlogs_slash(self, interaction: discord.Interaction):
        await self.bot.db.clear_logs(interaction.guild.id)
        await interaction.response.send_message(
            embed=embed(f"{icon('ok')} All mod logs cleared for this server.", color="success"))

    # ── Discord event listeners ────────────────────────────────
    async def send_to_log(self, guild, embed_obj):
        config = await self.bot.db.get_config(guild.id)
        ch_id = config.get("log_channel_id")
        if ch_id:
            ch = guild.get_channel(int(ch_id))
            if ch:
                try:
                    await ch.send(embed=embed_obj)
                except discord.HTTPException:
                    pass

    @commands.Cog.listener()
    async def on_member_join(self, member):
        e = embed(f"{icon('log_join')} Member Joined", color="success")
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name="User",            value=f"{member.mention} (`{member.id}`)")
        e.add_field(name="Account Created", value=member.created_at.strftime("%Y-%m-%d"))
        await self.send_to_log(member.guild, e)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        e = embed(f"{icon('log_leave')} Member Left", color="error")
        e.add_field(name="User", value=f"{member} (`{member.id}`)")
        await self.send_to_log(member.guild, e)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot or not message.guild:
            return
        e = embed(f"{icon('log_msg_del')} Message Deleted", color="warn")
        e.add_field(name="Author",  value=message.author.mention,           inline=True)
        e.add_field(name="Channel", value=message.channel.mention,          inline=True)
        e.add_field(name="Content", value=message.content[:1000] or "*empty*", inline=False)
        await self.send_to_log(message.guild, e)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot or not before.guild or before.content == after.content:
            return
        e = embed(f"{icon('log_msg_edit')} Message Edited", color="info")
        e.add_field(name="Author",  value=before.author.mention,           inline=True)
        e.add_field(name="Channel", value=before.channel.mention,          inline=True)
        e.add_field(name="Before",  value=before.content[:500] or "*empty*", inline=False)
        e.add_field(name="After",   value=after.content[:500]  or "*empty*", inline=False)
        await self.send_to_log(before.guild, e)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if not before.guild:
            return
        if before.nick != after.nick:
            e = embed(f"{icon('log_nick')} Nickname Changed", color="info")
            e.add_field(name="User",   value=after.mention,              inline=True)
            e.add_field(name="Before", value=before.nick or before.name, inline=True)
            e.add_field(name="After",  value=after.nick  or after.name,  inline=True)
            await self.send_to_log(before.guild, e)

        added_roles   = [r for r in after.roles  if r not in before.roles]
        removed_roles = [r for r in before.roles if r not in after.roles]
        if added_roles or removed_roles:
            e = embed(f"{icon('log_roles')} Roles Updated", color="info")
            e.add_field(name="User", value=after.mention, inline=False)
            if added_roles:
                e.add_field(name="Roles Added",
                            value=" ".join(r.mention for r in added_roles), inline=False)
            if removed_roles:
                e.add_field(name="Roles Removed",
                            value=" ".join(r.mention for r in removed_roles), inline=False)
            await self.send_to_log(before.guild, e)


async def setup(bot):
    await bot.add_cog(Logs(bot))
