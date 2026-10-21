"""Discovery and personal-library slash commands."""

import random

import discord
from discord import app_commands
from discord.ext import commands

from .catalog import BY_SLUG, CATEGORIES, PLATFORMS, TOOLS, find_tool, search_tools
from .ui import BrowseView, ToolView, embed, installation, profile, safe


async def autocomplete(interaction, current):
    return [
        app_commands.Choice(name=t["name"], value=t["slug"]) for t in search_tools(current)[:25]
    ]


class Atlas(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def browse(self, interaction, tools, title):
        view = BrowseView(tools, interaction.user.id, self.bot.db, title)
        await interaction.response.send_message(embed=view.render(), view=view if tools else None)

    @app_commands.command(description="Browse the complete atlas with filters and pagination")
    @app_commands.choices(
        category=[app_commands.Choice(name=c, value=c) for c in CATEGORIES],
        platform=[app_commands.Choice(name=p, value=p) for p in PLATFORMS],
    )
    async def explore(
        self,
        interaction: discord.Interaction,
        category: str | None = None,
        platform: str | None = None,
    ):
        await self.browse(
            interaction,
            search_tools(category=category, platform=platform),
            category or "Tool explorer",
        )

    @app_commands.command(description="Find tools by name, purpose, or discipline")
    async def search(
        self, interaction: discord.Interaction, query: app_commands.Range[str, 2, 100]
    ):
        await self.browse(interaction, search_tools(query), f"Search · {safe(query)}")

    @app_commands.command(description="Open a detailed tool profile and installation selector")
    @app_commands.autocomplete(name=autocomplete)
    async def tool(self, interaction: discord.Interaction, name: str):
        tool = find_tool(name)
        if not tool:
            await interaction.response.send_message(
                "No matching tool. Try `/search`.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            embed=profile(tool), view=ToolView(tool, interaction.user.id, self.bot.db)
        )

    @app_commands.command(description="Show installation guidance for your operating system")
    @app_commands.autocomplete(name=autocomplete)
    @app_commands.choices(platform=[app_commands.Choice(name=p, value=p) for p in PLATFORMS])
    async def install(self, interaction: discord.Interaction, name: str, platform: str):
        tool = find_tool(name)
        if not tool:
            await interaction.response.send_message("Unknown tool. Try `/search`.", ephemeral=True)
            return
        if platform not in tool["install"]:
            await interaction.response.send_message(
                f"No guide for this platform. See the official documentation: {tool['docs']}",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(embed=installation(tool, platform))

    @app_commands.command(description="Discover a random tool from the atlas")
    async def randomtool(self, interaction: discord.Interaction):
        tool = random.choice(TOOLS)
        await interaction.response.send_message(
            embed=profile(tool), view=ToolView(tool, interaction.user.id, self.bot.db)
        )

    @app_commands.command(description="See all disciplines and their catalog sizes")
    async def categories(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=embed(
                "🔱 Choose your discipline",
                "\n".join(f"**{c}** · {len(search_tools(category=c))} tools" for c in CATEGORIES),
            )
        )

    @app_commands.command(description="Open your private saved tools across servers")
    async def saved(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        slugs = await self.bot.db.bookmarks(interaction.user.id)
        tools = [BY_SLUG[s] for s in slugs if s in BY_SLUG]
        view = BrowseView(tools, interaction.user.id, self.bot.db, "Your saved tools")
        await interaction.followup.send(
            embed=view.render(), view=view if tools else None, ephemeral=True
        )

    @app_commands.command(description="Compare two tools by purpose, platform, and experience")
    @app_commands.autocomplete(first=autocomplete, second=autocomplete)
    async def compare(self, interaction: discord.Interaction, first: str, second: str):
        tools = [find_tool(first), find_tool(second)]
        if not all(tools):
            await interaction.response.send_message(
                "Choose two tools from autocomplete.", ephemeral=True
            )
            return
        result = embed(
            "⚖ Tool comparison",
            "Choose by your task and platform. Open `/tool` for installation details.",
        )
        for tool in tools:
            result.add_field(
                name=tool["name"],
                value=f"{tool['summary']}\n\n**{tool['category']}** · {tool['level']}\n{' · '.join(tool['platforms'])}\n[Documentation]({tool['docs']})",
                inline=True,
            )
        await interaction.response.send_message(embed=result)

    @app_commands.command(
        name="help", description="Get oriented: discovery, installation, bookmarks, and team review"
    )
    async def help_command(self, interaction: discord.Interaction):
        result = embed(
            "🔱 Welcome aboard POSEIDON",
            "Your team’s shared atlas for development and security.\nStart with **/explore** or search for a problem you want to solve.",
        )
        for name, value in [
            (
                "01 · Discover",
                "`/explore` filter and browse every page\n`/search` search names and purpose\n`/categories` · `/randomtool`",
            ),
            (
                "02 · Choose & install",
                "`/tool` profile, official docs, platform selector\n`/install` OS-specific guidance\n`/compare` compare two options",
            ),
            (
                "03 · Keep & contribute",
                "Use **Save / unsave** on a profile\n`/saved` your private cross-server library\n`/submit` suggest a resource for your server",
            ),
            (
                "04 · Team operations",
                "`/poseidon status` health\n`/poseidon review` · `/poseidon decide`\nReview requires Manage Server permission.",
            ),
        ]:
            result.add_field(name=name, value=value, inline=False)
        result.set_footer(
            text="Global slash commands · No message-content intent · No command execution"
        )
        await interaction.response.send_message(embed=result, ephemeral=True)
