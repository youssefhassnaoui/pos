import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from poseidon.bot import Poseidon
from poseidon.catalog import CATEGORIES, PLATFORMS, TOOLS, find_tool, search_tools
from poseidon.commands import Atlas
from poseidon.db import Database, SubmissionLimit
from poseidon.moderation import Moderation
from poseidon.security import public_https_url, text_input
from poseidon.ui import BrowseView, ToolView, installation, profile


class CatalogTests(unittest.TestCase):
    def test_catalog_contract_and_discord_limits(self):
        self.assertGreaterEqual(len(TOOLS), 70)
        self.assertEqual(len(TOOLS), len({t["slug"] for t in TOOLS}))
        self.assertLessEqual(len(CATEGORIES), 25)
        for tool in TOOLS:
            with self.subTest(tool=tool["slug"]):
                self.assertIs(find_tool(tool["name"]), tool)
                for key in ("website", "docs"):
                    public_https_url(tool[key])
                self.assertEqual(set(tool["install"]), set(tool["platforms"]))
                self.assertTrue(set(tool["platforms"]) <= set(PLATFORMS))
                for result in [profile(tool), *(installation(tool, p) for p in tool["install"])]:
                    self.assertLessEqual(len(result), 6000)
                    self.assertLessEqual(len(result.description or ""), 4096)
                    for field in result.fields:
                        self.assertLessEqual(len(field.value), 1024)

    def test_search_intersects_terms_and_filters(self):
        self.assertEqual([t["slug"] for t in search_tools("python lint")], ["ruff"])
        self.assertTrue(all(t["category"] == "Learning" for t in search_tools(category="Learning")))
        self.assertTrue(all("Web" in t["platforms"] for t in search_tools(platform="Web")))
        self.assertEqual(search_tools("no-such-tool-xyz"), [])

    def test_url_boundaries(self):
        for value in (
            "http://example.com",
            "https://localhost",
            "https://127.0.0.1",
            "https://10.0.0.1/a",
            "https://user:secret@example.com",
            "https://example.com:444",
            "https://example.com/\nspoof",
            "https://example.com/`spoof",
            "https://[::1]",
            "https://x.local",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                public_https_url(value)
        self.assertEqual(public_https_url("https://example.com/docs"), "https://example.com/docs")
        with self.assertRaises(ValueError):
            text_input("   ", 80, "Name")


class AsyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "state.db")
        await self.db.initialize()

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def test_review_tenant_isolation_and_audit(self):
        sid = await self.db.submit(10, 100, "Tool", "https://example.com", "Useful")
        self.assertEqual(await self.db.pending(20), [])
        self.assertFalse(await self.db.review(20, sid, 200, "approved"))
        self.assertTrue(await self.db.review(10, sid, 200, "approved"))
        self.assertFalse(await self.db.review(10, sid, 200, "rejected"))
        self.assertEqual(await self.db.pending(10), [])
        with self.assertRaises(ValueError):
            await self.db.review(10, sid, 200, "arbitrary")

    async def test_submission_limit_duplicates_and_concurrency(self):
        await self.db.submit(1, 2, "Name", "https://example.com/0", "Reason")
        with self.assertRaises(SubmissionLimit):
            await self.db.submit(1, 3, "Name", "https://example.com/0", "Reason")
        outcomes = await asyncio.gather(
            *(
                self.db.submit(1, 2, "Name", f"https://example.com/{i}", "Reason")
                for i in range(1, 8)
            ),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(v, int) for v in outcomes), 4)
        self.assertEqual(sum(isinstance(v, SubmissionLimit) for v in outcomes), 3)
        self.assertEqual(len(await self.db.pending(1)), 5)

    async def test_bookmarks_private_and_persistent(self):
        self.assertTrue(await self.db.toggle_bookmark(1, "git"))
        self.assertEqual(await self.db.bookmarks(2), [])
        await self.db.initialize()
        self.assertEqual(await self.db.bookmarks(1), ["git"])
        self.assertFalse(await self.db.toggle_bookmark(1, "git"))
        self.assertEqual(await self.db.bookmarks(1), [])

    async def test_pagination_reaches_every_tool_and_honors_results(self):
        view = BrowseView(TOOLS, 1, self.db)
        seen = set()
        for page in range(view.pages):
            view.page = page
            view.refresh()
            select = next(c for c in view.children if hasattr(c, "lookup"))
            seen.update(select.lookup)
            self.assertLessEqual(len(select.options), 25)
            self.assertLessEqual(len(view.render()), 6000)
        self.assertEqual(seen, {t["slug"] for t in TOOLS})
        filtered = search_tools("python")
        view = BrowseView(filtered, 1, self.db)
        seen = next(c for c in view.children if hasattr(c, "lookup")).lookup
        self.assertEqual(set(seen), {t["slug"] for t in filtered})
        self.assertLessEqual(len(BrowseView([], 1, self.db).render()), 6000)

    async def test_component_ownership_and_navigation(self):
        view = BrowseView(TOOLS, 1, self.db)
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=2),
            response=SimpleNamespace(send_message=AsyncMock(), edit_message=AsyncMock()),
        )
        self.assertFalse(await view.interaction_check(interaction))
        interaction.user.id = 1
        self.assertTrue(await view.interaction_check(interaction))
        await view.next_page.callback(interaction)
        self.assertEqual(view.page, 1)
        await view.previous.callback(interaction)
        self.assertEqual(view.page, 0)
        interaction.response.edit_message.assert_awaited()
        self.assertLessEqual(len(ToolView(TOOLS[0], 1, self.db).children), 25)

    async def test_command_registration_and_serialization(self):
        bot = Poseidon(Path(self.temp.name) / "bot.db")
        try:
            await bot.add_cog(Atlas(bot))
            await bot.add_cog(Moderation(bot))
            payload = [cmd.to_dict(bot.tree) for cmd in bot.tree.get_commands()]
            json.dumps(payload)
            names = {cmd["name"] for cmd in payload}
            self.assertTrue(
                {"explore", "install", "saved", "compare", "help", "submit", "poseidon"} <= names
            )
            moderation = bot.get_cog("Moderation")
            for name in ("review", "decide"):
                command = moderation.admin.get_command(name)
                self.assertTrue(command.guild_only)
                self.assertTrue(command.default_permissions.manage_guild)
                self.assertTrue(command.checks)
            self.assertFalse(bot.intents.message_content)
            self.assertFalse(bot.allowed_mentions.everyone)
        finally:
            await bot.close()

    async def test_search_command_response_matches_query(self):
        bot = Poseidon(Path(self.temp.name) / "bot.db")
        try:
            atlas = Atlas(bot)
            interaction = SimpleNamespace(
                user=SimpleNamespace(id=1), response=SimpleNamespace(send_message=AsyncMock())
            )
            await Atlas.search.callback(atlas, interaction, "python lint")
            kwargs = interaction.response.send_message.call_args.kwargs
            self.assertEqual([t["slug"] for t in kwargs["view"].tools], ["ruff"])
        finally:
            await bot.close()


if __name__ == "__main__":
    unittest.main()
