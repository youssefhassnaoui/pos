"""Reusable Discord presentation components, bounded to API limits."""

import math

import discord

COLOR = discord.Color.from_rgb(24, 184, 176)
FOOTER = "POSEIDON  /  TEAM TOOL ATLAS"
PAGE_SIZE = 8


def safe(value):
    return discord.utils.escape_markdown(discord.utils.escape_mentions(str(value)))


def embed(title, description=None):
    result = discord.Embed(title=title[:256], description=description, color=COLOR)
    result.set_footer(text=FOOTER)
    return result


def profile(tool):
    result = embed(f"🔱 {tool['name']}", f"{tool['summary']}\n\n**Explore → install → learn**")
    result.add_field(name="Discipline", value=tool["category"])
    result.add_field(name="Experience", value=tool["level"])
    result.add_field(name="Platforms", value=" · ".join(tool["platforms"]), inline=False)
    result.add_field(name="Start here", value=f"```text\n{tool['example']}\n```", inline=False)
    result.add_field(
        name="Source of truth",
        value=f"[Official site]({tool['website']}) · [Documentation]({tool['docs']})",
        inline=False,
    )
    result.set_footer(text=f"{FOOTER}  •  /tool {tool['slug']}")
    return result


def installation(tool, platform):
    result = embed(f"↓ {tool['name']} · {platform}", f"```text\n{tool['install'][platform]}\n```")
    result.add_field(
        name="Before you install",
        value=f"Check the [official guide]({tool['docs']}) for supported versions and prerequisites. Package availability varies by OS release. Commands are displayed only.",
        inline=False,
    )
    return result


class OwnedView(discord.ui.View):
    def __init__(self, owner_id):
        super().__init__(timeout=300)
        self.owner_id = owner_id

    async def interaction_check(self, interaction):
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            "Open your own explorer with `/explore` to use these controls.", ephemeral=True
        )
        return False

    async def on_error(self, interaction, error, item):
        import logging

        logging.getLogger("poseidon").exception("Component failed", exc_info=error)
        message = "This action could not finish. Try opening the command again."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


class InstallSelect(discord.ui.Select):
    def __init__(self, tool):
        self.tool = tool
        super().__init__(
            placeholder="Installation · choose your platform",
            options=[discord.SelectOption(label=p) for p in tool["install"]],
        )

    async def callback(self, interaction):
        await interaction.response.send_message(
            embed=installation(self.tool, self.values[0]), ephemeral=True
        )


class ToolView(OwnedView):
    def __init__(self, tool, owner_id, database):
        super().__init__(owner_id)
        self.tool, self.database = tool, database
        self.add_item(InstallSelect(tool))
        self.add_item(discord.ui.Button(label="Official site ↗", url=tool["website"]))
        self.add_item(discord.ui.Button(label="Documentation ↗", url=tool["docs"]))

    @discord.ui.button(label="☆ Save / unsave", style=discord.ButtonStyle.secondary, row=2)
    async def bookmark(self, interaction, button):
        await interaction.response.defer(ephemeral=True)
        try:
            added = await self.database.toggle_bookmark(interaction.user.id, self.tool["slug"])
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        await interaction.followup.send(
            "Saved to `/saved`." if added else "Removed from your bookmarks.", ephemeral=True
        )


class BrowseSelect(discord.ui.Select):
    def __init__(self, tools, database, owner_id):
        self.lookup = {t["slug"]: t for t in tools}
        self.database, self.owner_id = database, owner_id
        super().__init__(
            placeholder="Open a tool profile",
            options=[
                discord.SelectOption(
                    label=t["name"], value=t["slug"], description=t["summary"][:100]
                )
                for t in tools
            ],
        )

    async def callback(self, interaction):
        tool = self.lookup[self.values[0]]
        await interaction.response.send_message(
            embed=profile(tool), view=ToolView(tool, self.owner_id, self.database), ephemeral=True
        )


class BrowseView(OwnedView):
    def __init__(self, tools, owner_id, database, title="Tool explorer"):
        super().__init__(owner_id)
        self.tools, self.database, self.title = list(tools), database, title
        self.page = 0
        self.refresh()

    @property
    def pages(self):
        return max(1, math.ceil(len(self.tools) / PAGE_SIZE))

    def refresh(self):
        for child in list(self.children):
            if isinstance(child, BrowseSelect):
                self.remove_item(child)
        chunk = self.tools[self.page * PAGE_SIZE : (self.page + 1) * PAGE_SIZE]
        if chunk:
            select = BrowseSelect(chunk, self.database, self.owner_id)
            select.row = 0
            self.add_item(select)
        self.previous.disabled = self.page == 0
        self.next_page.disabled = self.page >= self.pages - 1
        self.counter.label = f"{self.page + 1} / {self.pages}"

    def render(self):
        chunk = self.tools[self.page * PAGE_SIZE : (self.page + 1) * PAGE_SIZE]
        description = f"**{len(self.tools)} results** · Choose a tool for its install guide and resources.\n\n"
        description += (
            "\n\n".join(f"**{t['name']}** · {t['category']}\n{t['summary']}" for t in chunk)
            or "No matching tools. Try a broader search."
        )
        result = embed(f"🌊 {self.title}", description)
        result.set_footer(
            text=f"{FOOTER}  •  Page {self.page + 1}/{self.pages}  •  Controls expire after 5 minutes"
        )
        return result

    @discord.ui.button(label="← Previous", row=1)
    async def previous(self, interaction, button):
        self.page = max(0, self.page - 1)
        self.refresh()
        await interaction.response.edit_message(embed=self.render(), view=self)

    @discord.ui.button(label="1 / 1", disabled=True, row=1)
    async def counter(self, interaction, button):
        pass

    @discord.ui.button(label="Next →", row=1)
    async def next_page(self, interaction, button):
        self.page = min(self.pages - 1, self.page + 1)
        self.refresh()
        await interaction.response.edit_message(embed=self.render(), view=self)
