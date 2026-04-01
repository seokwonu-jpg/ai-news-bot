# AI News Bot

Quick runbook for the daily briefing bot and urgent alert bot.

## Current operating mode

- Daily auto-send is enabled at `09:17 KST` via `.github/workflows/daily-news.yml`.
- Alert auto-send is not part of the active operating flow.
- The recommended entry point for validation is `newsbot.py`.
- Start with `--dry-run` and inspect the preview payload before re-enabling any scheduled delivery.
- Daily runs fail loudly when `0` articles are fetched, so feed/network failures do not silently look green.
- Daily runs may reuse the latest fetched articles when there are no unseen candidates, so the scheduled briefing does not skip a day unnecessarily.

## Setup

1. Copy `.env.example` to `.env`.
2. Fill in `SLACK_WEBHOOK_URL`.
3. Optionally fill in `SLACK_ALERT_WEBHOOK_URL`.
4. Optionally fill in `GEMINI_API_KEY`.
5. Optionally switch `LLM_PROVIDER=litellm` and fill in `LITELLM_API_KEY`.
6. Leave the default Gemini profile as-is unless you have a clear tuning goal.

Without `GEMINI_API_KEY`, the bot still runs with heuristic scoring and summary fallbacks.

The daily and alert pipelines now add a Kanta-fit score plus a Kanta work-area allowlist and product-proof gating for Product Hunt, so generic agent listings do not dominate the briefing.

## LLM providers

- Default provider: `gemini`
- Optional gateway provider: `litellm`
- Global override: `LLM_PROVIDER=gemini|litellm`
- Task-specific overrides:
  - `LLM_CURATOR_PROVIDER`
  - `LLM_SUMMARIZER_PROVIDER`

When `litellm` is enabled, the bot reads:

- `LITELLM_API_KEY`
- `LITELLM_API_BASE`
- `LITELLM_MODEL`
- `LITELLM_CURATOR_MODEL`
- `LITELLM_SUMMARIZER_MODEL`

Local runs also support the same LiteLLM keychain entry used by the translation tool if `LITELLM_API_KEY` is not set explicitly.

## Recommended Gemini profile

- `GEMINI_CURATOR_MODEL=gemini-2.5-flash-lite`
- `GEMINI_SUMMARIZER_MODEL=gemini-2.5-flash`
- `GEMINI_MODEL`: optional shared override for both tasks

Why this profile:

- `flash-lite` is enough for structured ranking and JSON score extraction in the curator step.
- `flash` is a better fit for user-facing Korean summaries and action-oriented wording.
- `gemini-2.5-pro` is not the default recommendation here because it is slower and more expensive than this bot needs.

## Recommended LiteLLM profile

- `LLM_PROVIDER=litellm`
- `LITELLM_CURATOR_MODEL=gpt-5-mini`
- `LITELLM_SUMMARIZER_MODEL=gpt-5.4`

If you want an alternative summary candidate, `claude-sonnet-4.6` or `gemini-2.5-pro` are good A/B test options. Avoid preview models for scheduled runs.

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

Run the daily briefing live and still save a preview JSON:

```powershell
python newsbot.py daily --preview-path reports/daily-preview.json
```

Run urgent alerts:

```powershell
python alert_bot.py
```

Run urgent alerts via the unified v2 entry point:

```powershell
python newsbot.py alert --dry-run --preview-path reports/alert-preview.json
```

Compare summary quality across providers/models:

```powershell
python compare_summary_models.py --candidate-provider litellm --candidate-model gpt-5.4
```

Run RSS source health check:

```powershell
python source_healthcheck.py
```

Print source health as JSON:

```powershell
python source_healthcheck.py --json
```

Run deterministic URL dedupe tests:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```
