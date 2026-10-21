# 🔱 POSEIDON · Team Tool Atlas

A global Discord slash-command bot with **74 curated tools and learning resources** across development, cloud, code quality, security, forensics, and more. Filter by discipline or OS, browse every result, compare tools, and keep a private cross-server library.

## Run locally

Python 3.11+ is required. From the repository root:

```sh
python -m venv .venv
# Linux/macOS
. .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
cp .env.example .env
# Set POSEIDON_TOKEN privately in .env or inject it through your deployment environment.
python -m poseidon.bot
```

Never commit a token or paste one into a public channel. The bot fails early if no token is configured. SQLite is initialized automatically under `data/poseidon.db`; change `DATABASE_PATH` to a writable persistent volume when deploying. Keep one bot process per database. Back up SQLite with its backup API or stop the process before copying the database and associated WAL files.

## Install into your team’s servers

Create a **bot application** in the Discord Developer Portal. Use the OAuth2 URL Generator with `bot` and `applications.commands` scopes, and **View Channels, Send Messages, Embed Links** permissions. Administrator and privileged intents are unnecessary. Install the application into each intended server using the generated invite; global registration does not automatically join servers.

Leave `DEV_GUILD_ID` empty for **global slash commands**. For development, set it to your test server ID for guild-specific synchronization. After moving back to global mode, remove stale development guild commands through Discord’s command API if necessary. Commands propagate according to Discord’s behavior; avoid repeated restarts just to force synchronization. Direct-message support depends on your application’s installation/context settings; moderation is server-only.

## Commands

| Command | Purpose |
| --- | --- |
| `/help` | Guided onboarding and command reference |
| `/explore [category] [platform]` | Paginated, filtered atlas |
| `/categories` | Disciplines and tool counts |
| `/search query` | Match all search words across name, category, and purpose |
| `/tool name` | Profile, installation selector, official documentation, save button |
| `/install name platform` | Platform-specific commands or official setup guidance |
| `/compare first second` | Compare purpose, level, platforms, and docs |
| `/randomtool` | Discover something new |
| `/saved` | Private bookmarks shared across your servers |
| `/submit name url reason` | Suggest a resource for this server’s review queue |
| `/poseidon status` | Gateway latency, SDK version, and catalog size |
| `/poseidon review` | Oldest ten pending suggestions; Manage Server required |
| `/poseidon decide` | Audited approval/rejection; Manage Server required |

Explorer controls belong to the requesting user and expire after five minutes. Other users can open their own explorer. Tool details opened from browsing and bookmark confirmations are private. Up to 100 bookmarks per user are retained.

## Installation guidance and freshness

The atlas displays commands; **it never executes them**. Some tools require platform-specific prerequisites or official installers, so those entries link to the upstream guide rather than inventing a package command. Package-manager names and availability can change with OS releases. Confirm against the official documentation before installation. Platform listings indicate that a guide is provided, not that every OS/tool combination was installed and tested here. Debian’s `fd-find` and `bat` packages can expose `fdfind` and `batcat` binaries respectively.

Runtime versions were resolved against PyPI during this setup: discord.py **2.7.1**, python-dotenv **1.2.4**, aiosqlite **0.22.1**. `requirements.lock` pins the complete runtime environment; `requirements.txt` records supported direct dependency ranges. There is no claim of continuous compatibility with every future Discord change. Weekly Dependabot PRs, scheduled dependency auditing, and the Python CI matrix support maintenance; review and test updates before merging.

## Component architecture

- `bot.py`: lifecycle, minimal gateway intents, synchronization, error responses.
- `commands.py`: discovery, installation, comparison, onboarding, bookmarks.
- `moderation.py`: server-only submission and review commands.
- `ui.py`: shared embed cards, owner-bound views, pagination, platform selector.
- `catalog.py`: tool data and reusable search/lookup functions.
- `security.py`: text and public-HTTPS URL validation.
- `db.py`: parameterized persistence, tenant isolation, transactional limits.

To add tools, follow the existing catalog schema. Use official URLs, unique slugs, bounded summaries, supported category/platform names, and safe starting examples. Run the catalog contract tests. Keep categories under Discord’s 25 static-choice limit; if the taxonomy grows past this, migrate category selection to autocomplete. Accepted suggestions remain in the audit queue; maintainers curate the catalog separately. Approval never imports code or auto-publishes links.

## Security and privacy

Mentions are disabled globally. Community text is escaped in moderator embeds; URLs reject credentials, local/private literal addresses, custom ports, and formatting/control characters. Submitted URLs are never fetched, so DNS resolution is not used as a trust signal. Moderators must still verify destination reputation; a public HTTPS URL can be malicious.

Every review query and decision is scoped to the current server and protected by runtime Manage Server checks. Parameterized SQL avoids query injection. A transaction enforces five suggestions per user per server per hour, blocks duplicate pending URLs, and prevents races. A short slash-command cooldown reduces repeated calls. This is a resource-discovery bot, not a shell, scanner, or execution agent.

SQLite stores Discord server/user/reviewer IDs, suggestions, decision state, timestamps, and bookmark slugs. It stores no message history or bot token. Restrict filesystem access, define your team’s retention policy, and remove personal records through an administrator-operated database maintenance process if needed. There is no automated retention or user-data deletion command yet.

## Validate and maintain

```sh
python -m unittest discover -s tests -v
python -m pip check
# Optional development tools:
python -m pip install ruff pip-audit
ruff check .
ruff format --check .
pip-audit -r requirements.lock
```

Tests cover catalog/API limits, result filtering and pagination, owner-only components, command payload serialization, permissions metadata, private bookmarks, server isolation, review transitions, and concurrent submission limits. They run offline without a Discord token. Live gateway login, global synchronization, and actual client rendering require a real bot application and are separate deployment checks.

To refresh dependencies, resolve `requirements.txt` in a **clean** virtual environment, freeze runtime dependencies into `requirements.lock`, run checks and the live smoke test, and review the diff. Do not freeze development tools into the runtime lock.

Live smoke test: launch the bot, confirm the global sync and ready log, run `/help`, paginate `/explore`, open `/tool git`, view `/install`, save and remove a bookmark, then test review permissions with moderator and ordinary-member accounts in two servers. Do not run install commands as part of the smoke test.
