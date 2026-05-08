"""
lambdas/microsoft/lambda_function.py

Polls Microsoft Jobs every 15 min (business hours) / 30 min (off-hours)
for new Software Engineer roles in the USA posted in the last 24 hours.
Sends a single Telegram digest to the GAMMA Jobs channel.
"""

import json
import os
import re
import time
import boto3
import requests
from datetime import datetime, timezone

# ── Environment variables ─────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
DYNAMODB_TABLE   = os.environ["DYNAMODB_TABLE"]

# ── Microsoft Jobs API ────────────────────────────────────────────────────────
MICROSOFT_URL = "https://apply.careers.microsoft.com/api/pcsx/search"
SEARCH_PARAMS = {
    "domain":                "microsoft.com",
    "query":                 "software engineer",
    "location":              "United States",
    "sort_by":               "new",
    "filter_include_remote": 1,
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":     "application/json",
    "Referer":    "https://apply.careers.microsoft.com/",
}

# ── Config ────────────────────────────────────────────────────────────────────
SDE_PATTERN = re.compile(
    r'(software\s+eng[\w]*|SWE|SDE)',
    re.IGNORECASE
)
TTL_SECONDS  = 90 * 24 * 3600
SECONDS_24HR = 24 * 3600
MAX_PAGES    = 10   # safety limit — max 10 pages ~100 jobs

# ── AWS clients ───────────────────────────────────────────────────────────────
dynamodb = boto3.resource("dynamodb")
table    = dynamodb.Table(DYNAMODB_TABLE)


# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch_jobs() -> list[dict]:
    """Paginate through Microsoft Jobs API until all results fetched."""
    try:
        positions = []
        start     = 0
        pages     = 0
        session   = requests.Session()
        session.headers.update(HEADERS)

        while True:
            if pages >= MAX_PAGES:
                print(f"[INFO] Reached page limit of {MAX_PAGES}")
                break

            resp = session.get(
                MICROSOFT_URL,
                params={**SEARCH_PARAMS, "start": start},
                timeout=15,
            )
            pages += 1
            resp.raise_for_status()

            data  = resp.json().get("data", {})
            batch = data.get("positions", [])
            total = data.get("count", 0)

            if not batch:
                break

            positions.extend(batch)
            start += len(batch)
            print(f"[INFO] Fetched {start}/{total} Microsoft jobs")

            if start >= total:
                break

        print(f"[INFO] Total fetched: {len(positions)} Microsoft jobs")
        return positions

    except Exception as e:
        print(f"[ERROR] Fetch failed: {e}")
        return []


# ── Normalise ─────────────────────────────────────────────────────────────────

def normalise(job: dict) -> dict:
    """Map Microsoft API fields to standard shape."""
    job_id    = str(job.get("displayJobId", ""))
    locations = job.get("standardizedLocations") or job.get("locations") or []
    location  = " | ".join(locations) if locations else "N/A"
    return {
        "job_id":    f"microsoft_{job_id}",
        "title":     job.get("name", ""),
        "location":  location,
        "team":      job.get("department", "N/A"),
        "posted_ts": job.get("postedTs", 0),
        "url":       f"https://apply.careers.microsoft.com{job.get('positionUrl', '')}",
    }


# ── Filters ───────────────────────────────────────────────────────────────────

def is_sde_role(title: str) -> bool:
    matched = bool(SDE_PATTERN.search(title))
    if not matched:
        print(f"[SKIP] Title mismatch: {title}")
    return matched


def is_within_24hrs(job: dict) -> bool:
    posted_ts = job.get("posted_ts", 0)
    if not posted_ts:
        return False
    age = time.time() - posted_ts
    if age > SECONDS_24HR:
        print(f"[SKIP] Too old ({int(age/3600)}hrs): {job['title']}")
        return False
    return True


def is_usa_job(job: dict) -> bool:
    location = job.get("location", "")
    if ", US" in location or "United States" in location:
        return True
    print(f"[SKIP] Non-USA: {location}")
    return False


# ── DynamoDB ──────────────────────────────────────────────────────────────────

def is_seen(job_id: str) -> bool:
    try:
        resp = table.get_item(Key={"job_id": job_id})
        return "Item" in resp
    except Exception as e:
        print(f"[ERROR] DynamoDB get error: {e}")
        return False


def mark_seen(job: dict) -> None:
    ttl_ts = int(time.time()) + TTL_SECONDS
    try:
        table.put_item(Item={
            "job_id":   job["job_id"],
            "title":    job.get("title", "N/A"),
            "location": job.get("location", "N/A"),
            "team":     job.get("team", "N/A"),
            "url":      job.get("url", ""),
            "seen_at":  datetime.now(timezone.utc).isoformat(),
            "ttl":      ttl_ts,
        })
    except Exception as e:
        print(f"[ERROR] DynamoDB put error: {e}")


# ── Telegram ──────────────────────────────────────────────────────────────────

def build_digest(new_jobs: list[dict]) -> str:
    lines = []
    for i, job in enumerate(new_jobs, 1):
        lines.append(
            f"{i}. <b>{job.get('title', 'N/A')}</b>\n"
            f"   📍 {job.get('location', 'N/A')}\n"
            f"   🏢 {job.get('team', 'N/A')}\n"
            f"   🔗 <a href='{job.get('url', '')}'>Apply</a>"
        )
    return (
        f"🟦 <b>{len(new_jobs)} New Microsoft Role(s)!</b>\n\n"
        + "\n\n".join(lines)
    )


def send_telegram(text: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id":                  TELEGRAM_CHAT_ID,
        "text":                     text,
        "parse_mode":               "HTML",
        "disable_web_page_preview": True,
    }, timeout=10).raise_for_status()


# ── Handler ───────────────────────────────────────────────────────────────────

def lambda_handler(event, context):
    print(f"[INFO] gamma-jobs-microsoft started at {datetime.now(timezone.utc).isoformat()}")

    try:
        raw_jobs = fetch_jobs()
        new_jobs = []

        for raw in raw_jobs:
            job = normalise(raw)

            if not is_sde_role(job["title"]):
                continue
            if not is_within_24hrs(job):
                continue
            if not is_usa_job(job):
                continue
            if is_seen(job["job_id"]):
                print(f"[SKIP] Already seen: {job['title']}")
                continue

            new_jobs.append(job)
            mark_seen(job)
            print(f"[INFO] New: {job['title']} | {job['location']}")

        print(f"[INFO] Done — {len(new_jobs)} new job(s) out of {len(raw_jobs)} checked")

        if new_jobs:
            send_telegram(build_digest(new_jobs))
            print(f"[INFO] Digest sent for {len(new_jobs)} job(s)")
        else:
            print("[INFO] No new Microsoft jobs.")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "new_jobs": len(new_jobs),
                "checked":  len(raw_jobs),
            }),
        }

    except Exception as exc:
        try:
            send_telegram(f"⚠️ <b>gamma-jobs-microsoft — Error</b>\n\n<code>{exc}</code>")
        except Exception:
            pass
        raise