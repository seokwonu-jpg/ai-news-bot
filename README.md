# AI News Bot

Quick runbook for the daily briefing bot and urgent alert bot.

## Current operating mode

- Legacy daily auto-send is disabled in `.github/workflows/daily-news.yml`.
- The recommended entry point for validation is `newsbot.py`.
- Start with `--dry-run` and inspect the preview payload before re-enabling any scheduled delivery.

## Setup

1. Copy `.env.example` to `.env`.
2. Fill in `SLACK_WEBHOOK_URL`.
3. Optionally fill in `SLACK_ALERT_WEBHOOK_URL`.
4. Optionally fill in `GEMINI_API_KEY`.
5. Leave the default Gemini profile as-is unless you have a clear tuning goal.

Without `GEMINI_API_KEY`, the bot still runs with heuristic scoring and summary fallbacks.

The daily and alert pipelines now add a Kanta-fit score plus a Kanta work-area allowlist and product-proof gating for Product Hunt, so generic agent listings do not dominate the briefing.

## Recommended Gemini profile

- `GEMINI_CURATOR_MODEL=gemini-2.5-flash-lite`
- `GEMINI_SUMMARIZER_MODEL=gemini-2.5-flash`
- `GEMINI_MODEL`: optional shared override for both tasks

Why this profile:

- `flash-lite` is enough for structured ranking and JSON score extraction in the curator step.
- `flash` is a better fit for user-facing Korean summaries and action-oriented wording.
- `gemini-2.5-pro` is not the default recommendation here because it is slower and more expensive than this bot needs.

## Runtime knobs

- `DAILY_FETCH_HOURS`: lookback window for the daily briefing. Default: `24`
- `DAILY_TOP_N`: number of daily articles to send. Default: `8`
- `ALERT_FETCH_HOURS`: lookback window for urgent alerts. Default: `12`
- `ALERT_MAX_ITEMS`: max urgent alerts per run. Default: `3`
- `ALERT_MIN_SCORE`: alert threshold. Default: `6.0`
- `SOURCE_HEALTHCHECK_HOURS`: default lookback for source checks. Default: `168`

## Commands

Install dependencies:

```powershell
pip install -r requirements.txt
```

Run the daily briefing:

```powershell
python bot.py
```

Run the daily briefing via the unified v2 entry point:

```powershell
python newsbot.py daily --dry-run --preview-path reports/daily-preview.json
```

Run urgent alerts:

```powershell
python alert_bot.py
```

Run urgent alerts via the unified v2 entry point:

```powershell
python newsbot.py alert --dry-run --preview-path reports/alert-preview.json
```

Compare summary quality across Gemini models:

```powershell
python compare_summary_models.py --candidate-model gemini-2.5-pro
```

Run RSS source health check:

```powershell
python source_healthcheck.py
```

Print source health as JSON:

```powershell
python source_healthcheck.py --json
```
