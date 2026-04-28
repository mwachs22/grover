# Grover — Automated Daily Newspaper for Pacific Grove, CA

Grover scrapes public information sources in Pacific Grove, CA and publishes a daily newspaper via Ghost CMS. Built with Python, runs on GitHub Actions.

## How It Works

```
Web Scrapers ─┐
              ├──> Classifier → Claude Summarizer → Ghost Admin API → Grover (Ghost CMS)
Gmail Inbox  ─┘
YouTube API  ─┘
```

Each morning at 6am PT:
1. **Scrape** — city news, calendar, council page, police news, PGUSD calendar, PGUSD board, library, chamber events, chamber news
2. **Read email** — eNotify, Alert Monterey County, and other email-only sources
3. **Fetch YouTube** — city council meeting recordings from the past 14 days
4. **Classify & deduplicate** — merge identical items across sources, tag by section
5. **Summarize** — Claude transforms raw content into 2-4 paragraph news articles
6. **Publish** — routine items publish directly; major items go to drafts

## Prerequisites

- **Ghost CMS instance** — hosted on PikaPods or self-hosted. Admin API key needed.
- **Anthropic API key** — for Claude summaries
- **Google Cloud project** — with Gmail API enabled, for reading email-only sources
- **YouTube Data API key** — for fetching city council meeting recordings

## Setup

### 1. Clone and configure

```bash
git clone <repo-url> grover
cd grover
cp .env.example .env
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
playwright install-deps
```

### 3. Set environment variables

Edit `.env` with your keys:

| Variable | Description |
|---|---|
| `GHOST_API_URL` | Your Ghost CMS URL (e.g. `https://grover.yourdomain.com`) |
| `GHOST_ADMIN_API_KEY` | Ghost Admin API key (Settings > Integrations > Custom Integration) |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Full JSON string of Google service account credentials |
| `YOUTUBE_API_KEY` | YouTube Data API v3 key |
| `GMAIL_USER` | Gmail address to read (e.g. `grover-daily@gmail.com`) |
| `LOG_LEVEL` | `INFO` or `DEBUG` |

### 4. Gmail API Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or use existing)
3. Enable **Gmail API**
4. Create a **service account** (IAM > Service Accounts)
5. Grant it the role **Gmail API > Gmail Modifier**
6. Generate a JSON key — this is your `GOOGLE_SERVICE_ACCOUNT_JSON`
7. In your Gmail account settings, enable IMAP
8. (For service account access) Set up domain-wide delegation if using a Workspace account, or use OAuth with token persistence

### 5. Ghost CMS Setup

1. Set up Ghost on [PikaPods](https://pikapods.com) or self-hosted
2. Go to **Settings > Integrations > Add Custom Integration**
3. Name it `grover`
4. Copy the **Admin API Key**
5. Note your Ghost URL

### 6. Ghost Tags

Grover expects these tags to exist in Ghost (it creates them on first use):

- `City Hall`
- `Public Safety`
- `Schools`
- `Community Calendar`
- `Library & Culture`
- `Brief`
- `Announcement`
- `Alert`
- `Meeting`
- `Event`
- `Police`
- `Grover Daily`

### 7. Test locally

```bash
python -m src.pipeline --dry-run
```

This runs the full pipeline without publishing to Ghost. It prints what would be published.

## GitHub Actions

The workflow `.github/workflows/daily-pipeline.yml` runs daily at 6am PT.

### Required secrets

Add these to your GitHub repo **Settings > Secrets and variables > Actions**:

| Secret | Value |
|---|---|
| `GHOST_API_URL` | Your Ghost URL |
| `GHOST_ADMIN_API_KEY` | Ghost Admin API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Full JSON string from Google service account |
| `YOUTUBE_API_KEY` | YouTube Data API key |

### Manual trigger

You can also trigger the workflow manually from the GitHub Actions tab, with options:
- **dry_run**: Skip publishing, just log what would happen
- **enable_gmail**: Toggle Gmail reader on/off
- **enable_youtube**: Toggle YouTube on/off
- **enable_web**: Toggle web scrapers on/off

## Project Structure

```
grover/
├── .github/workflows/daily-pipeline.yml   # GitHub Actions
├── src/
│   ├── __init__.py
│   ├── config.py          # All source URLs, prompts, constants
│   ├── models.py          # Dataclasses (ScrapedItem, ClassifiedItem, Story)
│   ├── pipeline.py        # Main orchestrator
│   ├── classifier.py      # Dedup + section/urgency classification
│   ├── summarizer.py      # Claude LLM integration
│   ├── publisher.py       # Ghost Admin API client
│   ├── gmail_reader/
│   │   └── __init__.py    # Gmail API reader
│   └── scrapers/
│       ├── __init__.py    # Web scrapers for all sources
│       └── youtube.py     # YouTube Data API reader
├── pyproject.toml
├── requirements.txt
└── .env.example
```

## Adding a New Source

1. Add the URL to `src/config.py`
2. Write a scraper function in `src/scrapers/__init__.py` that returns `list[ScrapedItem]`
3. Register it in `SCRAPER_REGISTRY` at the bottom of `src/scrapers/__init__.py`
4. Add the base URL to `INGESTION_SOURCES` in `src/pipeline.py`

For email sources:
1. Add sender config to `EMAIL_SOURCES` in `src/config.py`
2. Subscribe the Grover Gmail address to the source

## License

MIT
