"""
lambdas/amazon/lambda_function.py

Polls Amazon Jobs every 15 min (business hours) / 30 min (off-hours)
for new SDE roles in the USA posted in the last 24 hours.
Sends a single Telegram digest to the GAMMA Jobs channel.
"""


import json
import os
import re
import boto3
import requests
from datetime import datetime, timezone

# ── Env vars (set in SAM template / Lambda console) ──────────────────────────
TELEGRAM_TOKEN   = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
DYNAMODB_TABLE   = os.environ["DYNAMODB_TABLE"]

# ── Amazon Jobs search params ─────────────────────────────────────────────────
AMAZON_JOBS_URL = "https://www.amazon.jobs/en/search.json"
SEARCH_PARAMS   = {
    "base_query":                "Software Development Engineer",
    "category[]":                "software-development",
    "job_type":                  "Full-Time",
    "normalized_country_code[]": "USA",   # confirmed working param (not country_name)
    "result_limit":              100,
    "sort":                      "recent",
}

# Mimic a real browser to avoid being blocked by Amazon's bot detection.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# Use a session to reuse connections
http_session = requests.Session()
http_session.headers.update(HEADERS)

# Regex to filter job titles to actual SDE roles.
# Catches "SDE", "Software Development Engineer", "Software Engineer", etc.
# Case-insensitive to handle mixed-case titles from the API.
SDE_PATTERN = re.compile(
    r'(SDE|software\s+dev[\w]*\s+eng[\w]*|software\s+engineer)',
    re.IGNORECASE
)

# TTL: keep job IDs for 90 days so DynamoDB auto-cleans old entries
TTL_SECONDS = 90 * 24 * 3600

dynamodb = boto3.resource("dynamodb")
table    = dynamodb.Table(DYNAMODB_TABLE)


# ── Filters ───────────────────────────────────────────────────────────────────

def is_sde_role(title: str) -> bool:
    """Return True only if the job title matches an SDE role."""
    matched = bool(SDE_PATTERN.search(title))
    if not matched:
        print(f"[SKIP] Title mismatch: {title}")
    return matched




def is_usa_job(job: dict) -> bool:
    country_code = job.get("country_code", "").upper()
    location     = job.get("location", "").lower()
    if country_code == "US":
        return True
    if "united states" in location or ", wa" in location:
        return True
    print(f"[SKIP] Non-USA: {location} (country_code={country_code})")
    return False


# ── Fetch jobs ────────────────────────────────────────────────────────────────

def fetch_jobs() -> list[dict]:
    """Call Amazon Jobs search API and return raw job list."""
    try:
        resp = http_session.get(
            AMAZON_JOBS_URL,
            params=SEARCH_PARAMS,
            timeout=15,
        )
        resp.raise_for_status()
        jobs = resp.json().get("jobs", [])
        print(f"[INFO] Fetched {len(jobs)} jobs from Amazon Careers")
        return jobs
    except Exception as e:
        print(f"[ERROR] Failed to fetch jobs: {e}")
        return []


# ── DynamoDB — per-job lookup (O(1) vs full scan) ─────────────────────────────

def is_seen(job_id: str) -> bool:
    """Check a single job ID — much faster than scanning the whole table."""
    try:
        resp = table.get_item(Key={"job_id": job_id})
        return "Item" in resp
    except Exception as e:
        print(f"[ERROR] DynamoDB get error: {e}")
        return False


def mark_seen(job: dict, job_id: str) -> None:
    """Persist a new job to DynamoDB with TTL so old entries self-expire."""
    ttl_ts = int(datetime.now(timezone.utc).timestamp()) + TTL_SECONDS
    try:
        table.put_item(Item={
            "job_id":      job_id,
            "title":       job.get("title", "N/A"),
            "location":    job.get("location", "N/A"),
            "team":        job.get("business_category", "N/A"),
            "posted_date": job.get("posted_date", "N/A"),
            "url":         f"https://amazon.jobs{job.get('job_path', '')}",
            "seen_at":     datetime.now(timezone.utc).isoformat(),
            "ttl":         ttl_ts,
        })
        print(f"[INFO] Marked seen: {job_id}")
    except Exception as e:
        print(f"[ERROR] DynamoDB put error: {e}")


# ── Telegram ──────────────────────────────────────────────────────────────────

def build_digest(new_jobs: list[dict]) -> str:
    lines = []
    for i, job in enumerate(new_jobs, 1):
        url = f"https://amazon.jobs{job.get('job_path', '')}"
        lines.append(
            f"{i}. <b>{job.get('title', 'N/A')}</b>\n"
            f"   📍 {job.get('location', 'N/A')}\n"
            f"   📅 {job.get('posted_date', 'N/A')}\n"
            f"   🔗 <a href='{url}'>Apply</a>"
        )

    return (
        f"🚨 <b>{len(new_jobs)} New Amazon SDE Role(s)!</b>\n\n"
        + "\n\n".join(lines)
    )


def send_telegram(text: str, gif_url: str = None) -> None:
    """Send an HTML-formatted message via Telegram Bot API."""
    if gif_url and len(text) <= 1024:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendAnimation"
        payload = {
            "chat_id":    TELEGRAM_CHAT_ID,
            "animation":  gif_url,
            "caption":    text,
            "parse_mode": "HTML",
        }
        resp = http_session.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id":                  TELEGRAM_CHAT_ID,
        "text":                     text,
        "parse_mode":               "HTML",
        "disable_web_page_preview": True,
    }
    resp = http_session.post(url, json=payload, timeout=10)
    resp.raise_for_status()


# ── Lambda entry point ────────────────────────────────────────────────────────

def lambda_handler(event, context):
    print(f"[INFO] Starting check at {datetime.now(timezone.utc).isoformat()}")

    try:
        jobs     = fetch_jobs()
        new_jobs = []

        for job in jobs:
            # Use 'id' field — confirmed from API response (fallback to id)
            job_id = str(job.get("id_icims") or job.get("id") or "")
            title  = job.get("title", "")

            if not job_id:
                continue
            if not is_sde_role(title):
                continue
            if not is_usa_job(job):
                continue
            if is_seen(job_id):
                print(f"[SKIP] Already seen: {title}")
                continue

            new_jobs.append(job)
            mark_seen(job, job_id)
            print(f"[INFO] Notified: {title} | {job.get('location')} | ID:{job_id}")

        print(f"[INFO] Done — {len(new_jobs)} new job(s) out of {len(jobs)} checked")

        if new_jobs:
            gif_url = "https://media.licdn.com/dms/image/v2/D5622AQGna2dSfHlYrQ/feedshare-shrink_800/B56Z4OuuyiIQAc-/0/1778363593261?e=1779926400&v=beta&t=MNbEphcx87bBtXZS2o8ieG29YERTEvc6IR7a6M7A_bg"
            send_telegram(build_digest(new_jobs), gif_url=gif_url)
            print(f"[INFO] Digest sent for {len(new_jobs)} job(s)")
        else:
            print("[INFO] No new jobs. Nothing to notify.")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "new_jobs": len(new_jobs),
                "checked":  len(jobs),
            }),
        }

    except Exception as exc:
        error_msg = f"⚠️ <b>gamma-jobs-amazon — Error</b>\n\n<code>{exc}</code>"
        try:
            send_telegram(error_msg)
        except Exception:
            pass   # don't mask the original exception
        raise
