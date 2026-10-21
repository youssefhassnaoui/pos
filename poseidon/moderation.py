"""Server-scoped review commands; approved suggestions never execute or auto-publish."""

import discord
from discord import app_commands
from discord.ext import commands

from .catalog import CATEGORIES, TOOLS
from .db import SubmissionLimit
from .security import public_https_url, text_input
from .ui import embed, safe


class Moderation(commands.Cog):
    admin = app_commands.Group(name="poseidon", description="Team moderation and bot health")

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(description="Suggest an official resource for your server moderators")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 15, key=lambda i: (i.guild_id, i.user.id))
    async def submit(
        self,
        interaction: discord.Interaction,
        name: app_commands.Range[str, 1, 80],
        url: app_commands.Range[str, 1, 400],
        reason: app_commands.Range[str, 1, 500],
    ):
        try:
            name = text_input(name, 80, "Name")
            reason = text_input(reason, 500, "Reason")
            url = public_https_url(url)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            submission_id = await self.bot.db.submit(
                interaction.guild_id, interaction.user.id, name, url, reason
            )
        except SubmissionLimit as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        await interaction.followup.send(
            f"Suggestion **#{submission_id}** queued for your server moderators. Approval does not automatically publish it.",
            ephemeral=True,
        )

    @admin.command(description="Check connection health and catalog statistics")
    async def status(self, interaction: discord.Interaction):
        result = embed(
            "🌊 POSEIDON · System health",
            "Global discovery · Private bookmarks · Server-scoped moderation",
        )
        result.add_field(name="Gateway", value=f"{self.bot.latency * 1000:.0f} ms")
        result.add_field(name="Tools / disciplines", value=f"{len(TOOLS)} / {len(CATEGORIES)}")
        result.add_field(name="Library", value=f"discord.py {discord.__version__}")
        result.add_field(
            name="Catalog freshness",
            value="Installation guidance is curated, not continuously verified. Use the official links for current releases.",
            inline=False,
        )
        await interaction.response.send_message(embed=result, ephemeral=True)

    @admin.command(description="List the oldest ten pending suggestions in this server")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def review(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        rows = await self.bot.db.pending(interaction.guild_id)
        result = embed(
            "📋 Team review queue",
            "Oldest ten pending items. Decisions are audited; catalog publication requires maintainer review."
            if rows
            else "Your queue is clear.",
        )
        for row in rows:
            result.add_field(
                name=f"#{row['id']} · {safe(row['name'])}"[:256],
                value=f"<{row['url']}>\n{safe(row['reason'])[:700]}",
                inline=False,
            )
        await interaction.followup.send(embed=result, ephemeral=True)

    @admin.command(description="Record an approval or rejection for your server")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.choices(
        decision=[
            app_commands.Choice(name="Approve", value="approved"),
            app_commands.Choice(name="Reject", value="rejected"),
        ]
    )
    async def decide(
        self,
        interaction: discord.Interaction,
        submission_id: app_commands.Range[int, 1],
        decision: str,
    ):
        await interaction.response.defer(ephemeral=True)
        ok = await self.bot.db.review(
            interaction.guild_id, submission_id, interaction.user.id, decision
        )
        await interaction.followup.send(
            f"Suggestion #{submission_id}: {decision}. Approved entries still require catalog curation."
            if ok
            else "No pending suggestion with that ID in this server.",
            ephemeral=True,
        )
