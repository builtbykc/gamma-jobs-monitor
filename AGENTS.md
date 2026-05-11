# AGENTS.md

**Cross-IDE Context for AI Agents (Kiro, Antigravity, Gemini CLI, Cursor, etc.)**

This document provides comprehensive context about the GAMMA Jobs Monitor project for AI coding assistants across different IDEs and platforms. Read this file first before making any code changes.

---

## Project Overview

**GAMMA Jobs Monitor** is a production-grade, serverless AWS pipeline that monitors job postings from Google, Apple, Meta, Microsoft, and Amazon (GAMMA) for Software Development Engineer roles in the USA. It sends real-time Telegram notifications with zero maintenance and near-zero cost.

### Key Facts
- **Tech Stack**: AWS Lambda (Python 3.13), DynamoDB, EventBridge, Telegram Bot API
- **Infrastructure**: AWS SAM (Serverless Application Model)
- **Architecture**: Modular Strategy Pattern (one Lambda per company)
- **Current Status**: Amazon ✅ functional, Microsoft 🚧 in progress, Google/Meta/Apple 📋 planned

---

## Quick Start for AI Agents

### Before Making Changes

1. **Read steering files** in `docs/`:
   - `structure.md` — Architecture and modular strategy pattern
   - `code-conventions.md` — Python/AWS best practices
   - `product-roadmap.md` — Vision and future plans

2. **Check existing specs** in `lambdas/*/README.md`:
   - Each lambda will have its own README.md for specs.

3. **Review current implementations**:
   - `lambdas/amazon/lambda_function.py` — Reference implementation (working)
   - `lambdas/microsoft/lambda_function.py` — Needs debugging

### Common Tasks

| Task | Files to Read | Files to Modify |
|------|---------------|-----------------|
| Fix Microsoft monitor | `lambdas/microsoft/lambda_function.py`, `lambdas/microsoft/README.md` | `lambdas/microsoft/lambda_function.py` |
| Add new company (Google/Meta/Apple) | `lambdas/amazon/lambda_function.py`, `template.yaml` | Create `lambdas/{company}/`, update `template.yaml` |
| Refactor to Strategy Pattern | All lambda files, `docs/structure.md` | Create `lambdas/shared/`, refactor all lambdas |
| Update infrastructure | `template.yaml` | `template.yaml` |
| Change polling schedule | `template.yaml` (EventBridge schedules) | `template.yaml` |

---

## Architecture Deep Dive

### High-Level Flow

```
EventBridge Schedule (every 15-30 min)
    ↓
Lambda Function (per company)
    ↓
1. FETCH     → Call company API with pagination
2. NORMALIZE → Map to standard Job schema
3. FILTER    → SDE role + USA location + 24hr freshness
4. DEDUPE    → Check DynamoDB (seen jobs)
5. NOTIFY    → Send Telegram digest
```

### Standard Job Schema

All scrapers normalize to this shape:

```python
{
    "job_id":    str,   # Unique ID from company API
    "title":     str,   # Job title
    "location":  str,   # Location string
    "team":      str,   # Department/team
    "posted_ts": int,   # Unix timestamp (seconds since epoch)
    "url":       str,   # Application URL
}
```

### Per-Company Resources

Each company gets:
- **Lambda Function**: `gamma-jobs-{company}`
- **DynamoDB Table**: `gamma-jobs-{company}-seen` (TTL: 90 days)
- **Telegram Bot Token**: `TelegramBotToken{Company}` (SAM parameter)
- **EventBridge Schedules**: Business hours (15 min), off-hours (30 min)
- **CloudWatch Alarm**: Monitors Lambda errors

### Shared Resources

- **Telegram Chat ID**: All bots post to the same channel

---

## Code Conventions (Quick Reference)

### Python Style

```python
# ✅ GOOD
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]  # Fail fast
resp = requests.get(url, timeout=15)  # Always timeout
print(f"[INFO] Fetched {len(jobs)} jobs")  # Structured logging

# ❌ BAD
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")  # Silent failure
resp = requests.get(url)  # No timeout
print("got jobs")  # Unstructured
```

### Lambda Best Practices

```python
# ✅ GOOD: Initialize outside handler (reused across invocations)
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(DYNAMODB_TABLE)

def lambda_handler(event, context):
    # Use pre-initialized resources
    pass

# ❌ BAD: Initialize inside handler (recreated every time)
def lambda_handler(event, context):
    dynamodb = boto3.resource("dynamodb")
```

### DynamoDB Operations

```python
# ✅ GOOD: Single-item lookup (O(1))
def is_seen(job_id: str) -> bool:
    resp = table.get_item(Key={"job_id": job_id})
    return "Item" in resp

# ❌ BAD: Full table scan (O(n))
def is_seen(job_id: str) -> bool:
    resp = table.scan()
    return job_id in [item["job_id"] for item in resp["Items"]]
```

### Error Handling

```python
# ✅ GOOD: Log and continue
try:
    table.put_item(Item=item)
except Exception as e:
    print(f"[ERROR] DynamoDB put error: {e}")
    # Continue processing other jobs

# ❌ BAD: Crash entire Lambda
table.put_item(Item=item)  # Unhandled exception
```

---

## Current Issues & Debugging

### Microsoft Monitor Failures

**Status**: Lambda deployed but experiencing errors

**Known Issues**:
- Pagination may not be working correctly
- Timestamp filtering needs validation (Unix vs string dates)
- Location filtering may be too strict/loose
- SDE title regex may need tuning

**Debugging Steps**:
1. Check CloudWatch logs: `sam logs -n gamma-jobs-microsoft --tail`
2. Test locally: `sam local invoke MicrosoftJobsFunction`
3. Compare API response structure to Amazon implementation
4. Add verbose logging for each filter stage

**Spec Reference**: `lambdas/microsoft/README.md`

---

## Testing & Deployment

### Local Testing

```bash
# Build SAM application
sam build

# Test a specific Lambda locally
sam local invoke MicrosoftJobsFunction

# Test with custom event
sam local invoke MicrosoftJobsFunction -e events/test-event.json
```

### Deployment

```bash
# First-time deployment (guided)
sam deploy --guided

# Subsequent deployments
sam build && sam deploy

# Deploy to specific stage
sam deploy --config-env production
```

### Manual Lambda Invocation

```bash
# Invoke deployed Lambda
aws lambda invoke \
  --function-name gamma-jobs-microsoft \
  --payload '{}' \
  response.json && cat response.json

# Check logs
sam logs -n gamma-jobs-microsoft --tail

# Check recent logs
sam logs -n gamma-jobs-microsoft --start-time '10min ago'
```

### DynamoDB Inspection

```bash
# Scan table for seen jobs
aws dynamodb scan \
  --table-name gamma-jobs-microsoft-seen \
  --query "Items[*].{ID:job_id.S,Title:title.S,SeenAt:seen_at.S}"

# Get specific job
aws dynamodb get-item \
  --table-name gamma-jobs-microsoft-seen \
  --key '{"job_id": {"S": "12345"}}'
```

---

## Common Patterns & Anti-Patterns

### Pagination

```python
# ✅ GOOD: Safety limit to prevent infinite loops
def fetch_jobs() -> list[dict]:
    positions = []
    start = 0
    pages = 0
    MAX_PAGES = 10

    while pages < MAX_PAGES:
        resp = session.get(url, params={"start": start})
        batch = resp.json().get("positions", [])
        if not batch:
            break
        positions.extend(batch)
        start += len(batch)
        pages += 1

    return positions

# ❌ BAD: Infinite loop risk
while True:
    resp = session.get(url, params={"start": start})
    batch = resp.json().get("positions", [])
    positions.extend(batch)
    start += len(batch)
```

### Timestamp Handling

```python
# ✅ GOOD: Normalize to Unix timestamp
def normalize(job: dict) -> dict:
    # Amazon: string date
    posted_str = job.get("posted_date", "")
    posted = datetime.strptime(posted_str, "%B %d, %Y")
    posted_ts = int(posted.timestamp())
    
    # Microsoft: already Unix timestamp
    posted_ts = job.get("postedTs", 0)
    
    return {"posted_ts": posted_ts, ...}

# ❌ BAD: Keep different formats
return {"posted_date": job.get("posted_date")}  # Inconsistent
```

### Filter Logging

```python
# ✅ GOOD: Log why jobs are skipped
def is_sde_role(title: str) -> bool:
    matched = bool(SDE_PATTERN.search(title))
    if not matched:
        print(f"[SKIP] Title mismatch: {title}")
    return matched

# ❌ BAD: Silent filtering
def is_sde_role(title: str) -> bool:
    return bool(SDE_PATTERN.search(title))
```

---

## Future Refactoring (Strategy Pattern)

### Current State (Duplicated Code)

Each Lambda has ~150 lines with duplicated logic:
- Fetch (company-specific)
- Normalize (company-specific)
- Filter (duplicated)
- Dedupe (duplicated)
- Notify (duplicated)

### Target State (Strategy Pattern)

```python
# Base class (shared logic)
class BaseScraper(ABC):
    @abstractmethod
    def fetch_jobs(self) -> list[dict]:
        """Company-specific API call."""
        pass
    
    @abstractmethod
    def normalize(self, job: dict) -> dict:
        """Company-specific field mapping."""
        pass
    
    def is_sde_role(self, title: str) -> bool:
        """Shared SDE filter."""
        return bool(SDE_PATTERN.search(title))
    
    def run(self) -> dict:
        """Shared execution flow."""
        jobs = self.fetch_jobs()
        for job in jobs:
            normalized = self.normalize(job)
            if self.is_sde_role(normalized["title"]):
                # ... filter, dedupe, notify
        return {"new_jobs": len(new_jobs), "checked": len(jobs)}

# Company implementation (5-10 lines)
class MicrosoftScraper(BaseScraper):
    def fetch_jobs(self) -> list[dict]:
        # Microsoft-specific pagination
        pass
    
    def normalize(self, job: dict) -> dict:
        # Microsoft-specific field mapping
        pass

# Lambda handler (1 line)
def lambda_handler(event, context):
    return MicrosoftScraper().run()
```

**Benefits**:
- 70% code reduction
- Bug fixes propagate to all scrapers
- New company = implement 2 methods

**Migration Plan**: See `docs/product-roadmap.md` Phase 3

---

## API Discovery Guide (For Adding New Companies)

### Step 1: Find the API

```bash
# 1. Visit careers page in browser
open https://www.metacareers.com/jobs

# 2. Open DevTools → Network tab → Filter "Fetch/XHR"
# 3. Search for jobs → Look for JSON API calls
# 4. Copy API URL and test

curl 'https://www.metacareers.com/api/jobs' \
  -H 'User-Agent: Mozilla/5.0...' \
  | jq '.'
```

### Step 2: Document Response Schema

```python
# Example: Map Meta API response to standard schema
{
    "id": "12345",                    # → job_id
    "title": "Software Engineer",     # → title
    "locations": ["Menlo Park, CA"],  # → location (join array)
    "department": "Infrastructure",   # → team
    "posted_date": "2024-01-15",      # → posted_ts (parse to Unix)
    "url": "/jobs/12345"              # → url (make absolute)
}
```

### Step 3: Implement Scraper

```python
# lambdas/meta/lambda_function.py
def fetch_jobs() -> list[dict]:
    # Meta-specific pagination
    pass

def normalise(job: dict) -> dict:
    return {
        "job_id":    str(job.get("id", "")),
        "title":     job.get("title", ""),
        "location":  " | ".join(job.get("locations", [])),
        "team":      job.get("department", "N/A"),
        "posted_ts": parse_meta_timestamp(job.get("posted_date")),
        "url":       f"https://www.metacareers.com{job.get('url', '')}",
    }
```

### Step 4: Add SAM Resources

```yaml
# template.yaml
MetaSeenJobsTable:
  Type: AWS::DynamoDB::Table
  Properties:
    TableName: gamma-jobs-meta-seen
    # ... (copy from Amazon/Microsoft)

MetaJobsFunction:
  Type: AWS::Serverless::Function
  Properties:
    FunctionName: gamma-jobs-meta
    CodeUri: lambdas/meta/
    # ... (copy from Amazon/Microsoft)
```

---

## Troubleshooting Guide

### Lambda Errors

**Symptom**: CloudWatch alarm triggered

**Steps**:
1. Check logs: `sam logs -n gamma-jobs-{company} --tail`
2. Look for `[ERROR]` messages
3. Common causes:
   - API schema changed (KeyError on field access)
   - Rate limiting (HTTP 429)
   - Timeout (increase Lambda timeout in template.yaml)
   - DynamoDB throttling (check table metrics)

### No Notifications

**Symptom**: Lambda runs successfully but no Telegram messages

**Steps**:
1. Check if new jobs were found: Look for `[INFO] Done — X new job(s)`
2. If X = 0, check filters:
   - Are jobs too old? (>24 hours)
   - Are jobs non-USA?
   - Are jobs non-SDE titles?
   - Are jobs already in DynamoDB?
3. If X > 0, check Telegram:
   - Verify bot token is correct
   - Verify chat ID is correct
   - Test with manual curl to Telegram API

### False Positives

**Symptom**: Non-SDE jobs trigger notifications

**Steps**:
1. Check job title against SDE regex: `software\s+eng[\w]*|SWE|SDE`
2. Refine regex to exclude:
   - "Software Engineering Manager" → Add negative lookahead
   - "Software Test Engineer" → Add "Development" requirement
3. Update `SDE_PATTERN` in lambda_function.py

### False Negatives

**Symptom**: Missing SDE jobs that should match

**Steps**:
1. Check CloudWatch logs for `[SKIP]` messages
2. Common causes:
   - Title regex too strict (expand pattern)
   - Location filter too strict (check for edge cases like "Remote, USA")
   - Timestamp parsing error (job appears >24h old)
3. Add verbose logging to identify which filter is rejecting

---

## Environment Variables

### Required (Set in template.yaml)

```yaml
Environment:
  Variables:
    TELEGRAM_BOT_TOKEN: !Ref TelegramBotToken{Company}
    TELEGRAM_CHAT_ID:   !Ref TelegramChatId
    DYNAMODB_TABLE:     !Ref {Company}SeenJobsTable
```

### Optional (For debugging)

```python
# Add to lambda_function.py for verbose logging
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

if DEBUG:
    print(f"[DEBUG] Raw API response: {resp.json()}")
```

---

## Security Considerations

### Secrets Management

- ✅ **DO**: Use SAM parameters with `NoEcho: true`
- ❌ **DON'T**: Hardcode bot tokens in code
- ❌ **DON'T**: Commit secrets to Git

### IAM Permissions

- ✅ **DO**: Use least-privilege policies (`DynamoDBCrudPolicy`)
- ❌ **DON'T**: Use wildcard permissions (`*`)

### API Keys

- ✅ **DO**: Rotate Telegram bot tokens periodically
- ✅ **DO**: Use separate bot tokens per company (easier to revoke)

---

## Performance Optimization

### Current Performance

| Metric | Value |
|--------|-------|
| Lambda duration | ~5-10 seconds |
| Lambda memory | 256 MB (sufficient) |
| DynamoDB reads | ~100/day per company |
| DynamoDB writes | ~10/day per company |
| Cost | ~$0.00/month (within free tier) |

### Optimization Tips

1. **Use ARM64**: 20% cost savings (already configured)
2. **Reuse connections**: Use `requests.Session()` (already implemented)
3. **Batch DynamoDB writes**: Use `batch_write_item` if >25 new jobs
4. **Cache API responses**: Store in `/tmp/` for retry logic

---

## Monitoring & Alerts

### CloudWatch Metrics

- **Lambda Errors**: Alarm triggers on ≥1 error in 5 minutes
- **Lambda Duration**: Monitor for timeouts (>60 seconds)
- **DynamoDB Throttles**: Monitor for capacity issues

### Telegram Error Notifications

All unhandled exceptions are sent to Telegram:

```python
try:
    # Main logic
    pass
except Exception as exc:
    error_msg = f"⚠️ <b>gamma-jobs-{company} — Error</b>\n\n<code>{exc}</code>"
    send_telegram(error_msg)
    raise  # Re-raise for CloudWatch alarm
```

---

## File Structure Reference

```
gamma-jobs-monitor/
├── docs/                      # Project guidance documents
│   ├── structure.md           # Architecture patterns
│   ├── code-conventions.md    # Python/AWS best practices
│   └── product-roadmap.md     # Vision & future plans
│
├── lambdas/
│   ├── amazon/
│   │   ├── lambda_function.py     # ✅ Working reference
│   │   └── requirements.txt
│   └── microsoft/
│       ├── lambda_function.py     # 🚧 Needs debugging
│       └── requirements.txt
│
├── template.yaml                  # AWS SAM infrastructure
├── samconfig.toml                 # SAM deployment config
├── AGENTS.md                      # This file
└── README.md                      # User documentation
```

---

## Quick Commands Cheatsheet

```bash
# Build & deploy
sam build && sam deploy

# Test locally
sam local invoke MicrosoftJobsFunction

# Check logs
sam logs -n gamma-jobs-microsoft --tail

# Invoke deployed Lambda
aws lambda invoke --function-name gamma-jobs-microsoft --payload '{}' response.json

# Scan DynamoDB
aws dynamodb scan --table-name gamma-jobs-microsoft-seen

# Delete stack
sam delete
```

---

## Contact & Resources

### Documentation
- AWS SAM: https://docs.aws.amazon.com/serverless-application-model/
- AWS Lambda: https://docs.aws.amazon.com/lambda/
- DynamoDB: https://docs.aws.amazon.com/dynamodb/
- Telegram Bot API: https://core.telegram.org/bots/api

### Project-Specific
- Steering files: `docs/`
- Current specs: `lambdas/*/README.md`
- Product roadmap: `docs/product-roadmap.md`

---

**Last Updated**: May 10, 2026

**For AI Agents**: This document is your starting point. Always read the steering files before making changes. Follow the code conventions strictly. When in doubt, reference the working Amazon implementation.
