# WHOOP Job Monitor

Monitors WHOOP careers for Data Science & Performance Science roles and emails you the current listings (and “new since last run”) on Saturday 8am, Sunday 8am, and Monday 5pm Pacific.

## Running locally

- **One-time:** `python whoop_job_monitor.py` (set `monitor.run_once()` in `main()`).
- **Scheduled (Sat 8am, Sun 8am, Mon 5pm Pacific):** `python whoop_job_monitor.py` with `monitor.run_scheduled()` in `main()`.

## GitHub Actions (free)

The workflow runs on a schedule and doesn’t require your laptop to be on.

### 1. Add repository secrets

In your repo: **Settings → Secrets and variables → Actions → New repository secret.**

| Secret | Required | Description |
|--------|----------|-------------|
| `WHOOP_SMTP_PASSWORD` | **Yes** | Gmail app password for sending email |
| `WHOOP_SENDER_EMAIL` | No | Sender address (default: in script) |
| `WHOOP_RECEIVER_EMAIL` | No | Recipient address (default: in script) |

### 2. Push the workflow

Push `.github/workflows/whoop-job-monitor.yml` (and the script changes). The workflow will run on the schedule and on **workflow_dispatch** (manual run from the Actions tab).

### 3. Schedule

- **Cron:** Saturday 16:00 UTC (8am Pacific), Sunday 16:00 UTC (8am Pacific), Monday 01:00 UTC (5pm Pacific).
- To change times, edit the `cron` expressions in the workflow and `SCHEDULE_SLOTS` in the script.

### 4. Cost

- **Public repo:** Free (2,000 minutes/month).
- **Private repo:** 2,000 minutes/month on the free plan. This job runs three times per week and stays within the free tier.
