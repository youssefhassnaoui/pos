"""Minimal application lifecycle. Run with python -m poseidon.bot."""

import logging
import os
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from .commands import Atlas
from .db import Database
from .moderation import Moderation

LOG = logging.getLogger("poseidon")


class Poseidon(commands.Bot):
    def __init__(self, database_path=None):
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.db = Database(database_path or os.getenv("DATABASE_PATH", "data/poseidon.db"))

    async def setup_hook(self):
        await self.db.initialize()
        await self.add_cog(Atlas(self))
        await self.add_cog(Moderation(self))
        guild_id = os.getenv("DEV_GUILD_ID", "").strip()
        if guild_id:
            if not guild_id.isdecimal() or int(guild_id) <= 0:
                raise ValueError("DEV_GUILD_ID must be a positive Discord server ID.")
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            LOG.info("Synced %s development commands", len(synced))
        else:
            synced = await self.tree.sync()
            LOG.info("Synced %s global commands", len(synced))

    async def on_ready(self):
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching, name="the team atlas · /help"
            )
        )
        LOG.info("POSEIDON ready (%s)", self.user.id)

    async def on_error(self, event_method, *args, **kwargs):
        LOG.exception("Discord event failed: %s", event_method)


async def handle_error(interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        message = "You need **Manage Server** permission for this command."
    elif isinstance(error, app_commands.CommandOnCooldown):
        message = f"Please try again in {error.retry_after:.0f} seconds."
    elif isinstance(error, app_commands.NoPrivateMessage):
        message = "Use this command inside a server."
    elif isinstance(error, app_commands.CheckFailure):
        message = "You cannot use this command here."
    else:
        # Avoid logging interaction input, URLs, or wrapped exceptions that may contain secrets.
        LOG.error("Slash command failed: %s", type(error).__name__)
        message = "This action could not finish. Please try again or contact a maintainer."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


def main():
    load_dotenv(Path.cwd() / ".env")
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    token = os.getenv("POSEIDON_TOKEN", "").strip()
    if not token or token == "PUT_YOUR_BOT_TOKEN_HERE":
        raise SystemExit(
            "Set POSEIDON_TOKEN securely in environment settings or an untracked .env file."
        )
    bot = Poseidon()
    bot.tree.on_error = handle_error
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
