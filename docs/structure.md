# Project Structure & Architecture

## Overview

GAMMA Jobs Monitor is a serverless AWS pipeline that polls job APIs from Google, Apple, Meta, Microsoft, and Amazon (GAMMA) for Software Development Engineer roles. The system uses a **modular Strategy Pattern** where each company is implemented as a standalone scraper module with consistent interfaces.

## Architecture Pattern

### Strategy Pattern for Scrapers

Each company scraper follows the same lifecycle:

```
┌─────────────────────────────────────────────────────────────┐
│                    Lambda Handler Entry                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  1. FETCH      → Paginate through company API               │
│  2. NORMALIZE  → Map to standard Job schema                 │
│  3. FILTER     → Apply SDE/USA/24hr filters                 │
│  4. DEDUPE     → Check DynamoDB for seen jobs               │
│  5. NOTIFY     → Send Telegram digest                       │
└─────────────────────────────────────────────────────────────┘
```

### Standard Job Schema

All scrapers normalize to this shape:

```python
{
    "job_id":    str,   # Unique job identifier from company API
    "title":     str,   # Job title
    "location":  str,   # Location string (may contain multiple locations)
    "team":      str,   # Department/team name
    "posted_ts": int,   # Unix timestamp (seconds since epoch)
    "url":       str,   # Application URL
}
```

**Note**: Job IDs do not need company prefixes since each company has its own isolated DynamoDB table.

## Directory Structure

```
gamma-jobs-monitor/
├── .kiro/
│   ├── specs/                    # Kiro spec documents
│   │   └── {feature-name}/
│   │       ├── .config.kiro
│   │       ├── requirements.md
│   │       ├── design.md
│   │       └── tasks.md
│   └── steering/                 # Project guidance documents
│       ├── structure.md          # This file
│       ├── code-conventions.md   # AWS/Python best practices
│       └── product-roadmap.md    # Future company integrations
│
├── lambdas/
│   ├── amazon/
│   │   ├── lambda_function.py    # Amazon scraper
│   │   └── requirements.txt      # Python dependencies
│   ├── microsoft/
│   │   ├── lambda_function.py    # Microsoft scraper
│   │   └── requirements.txt
│   └── {company}/                # Future: google, meta, apple
│       ├── lambda_function.py
│       └── requirements.txt
│
├── template.yaml                 # AWS SAM infrastructure-as-code
├── samconfig.toml                # SAM deployment config
├── AGENTS.md                     # Cross-IDE context for AI agents
└── README.md                     # User-facing documentation
```

## Infrastructure Components

### Per-Company Resources

Each company scraper gets:

1. **Lambda Function**
   - Runtime: Python 3.13 on ARM64
   - Timeout: 60 seconds
   - Memory: 256 MB
   - Triggered by EventBridge schedules

2. **DynamoDB Table**
   - Name: `gamma-jobs-{company}-seen`
   - Key: `job_id` (String)
   - TTL: 90 days (auto-cleanup)
   - Billing: Pay-per-request
   - **Isolation**: Each company has its own table (no cross-company deduplication)

3. **EventBridge Schedules**
   - **Business hours** (Mon-Fri 7AM-8PM EST): Every 15 minutes
   - **Off-hours** (all other times): Every 30 minutes

4. **CloudWatch Alarm**
   - Monitors Lambda errors
   - Threshold: ≥1 error in 5 minutes

5. **Telegram Bot Token**
   - **One bot per company** (e.g., `TelegramBotTokenAmazon`, `TelegramBotTokenMicrosoft`)
   - All bots send to the **same Telegram channel** (shared `TelegramChatId`)

### Shared Resources

- **Telegram Chat ID**: Single channel receives alerts from all company bots

## Scraper Lifecycle

### 1. Fetch Phase

**Responsibility**: Retrieve raw job data from company API

**Key Considerations**:
- Pagination handling (varies by API)
- Rate limiting and backoff
- User-Agent headers to avoid bot detection
- Timeout handling (15 seconds max)

**Example (Microsoft)**:
```python
def fetch_jobs() -> list[dict]:
    positions = []
    start = 0
    while True:
        resp = session.get(API_URL, params={"start": start})
        batch = resp.json().get("data", {}).get("positions", [])
        if not batch:
            break
        positions.extend(batch)
        start += len(batch)
    return positions
```

### 2. Normalize Phase

**Responsibility**: Map company-specific API response to standard Job schema

**Key Considerations**:
- Field name mapping (e.g., `displayJobId` → `job_id`)
- Timestamp normalization (string dates vs Unix timestamps)
- Location formatting (arrays vs strings)
- URL construction (relative vs absolute paths)

**Example (Microsoft)**:
```python
def normalise(job: dict) -> dict:
    return {
        "job_id":    str(job.get("displayJobId", "")),
        "title":     job.get("name", ""),
        "location":  " | ".join(job.get("standardizedLocations", [])),
        "team":      job.get("department", "N/A"),
        "posted_ts": job.get("postedTs", 0),
        "url":       f"https://apply.careers.microsoft.com{job.get('positionUrl')}",
    }
```

### 3. Filter Phase

**Responsibility**: Apply business logic to identify relevant jobs

**Standard Filters**:
1. **SDE Role Filter**: Regex match on title
   - Pattern: `software\s+eng[\w]*|SWE|SDE` (case-insensitive)
   - Catches: "Software Engineer", "SDE", "Software Development Engineer"

2. **USA Location Filter**: Check location string
   - Patterns: `, US`, `United States`, `country_code == "US"`

3. **24-Hour Freshness Filter**: Check posted timestamp
   - Logic: `current_time - posted_ts <= 86400 seconds`

**Logging**: Each filter logs skipped jobs for debugging

### 4. Dedupe Phase

**Responsibility**: Prevent duplicate notifications using DynamoDB

**Operations**:
- **Check**: `table.get_item(Key={"job_id": job_id})`
- **Mark**: `table.put_item(Item={...job, "ttl": now + 90_days})`

**TTL Strategy**: Jobs auto-expire after 90 days to keep table size bounded

**Isolation**: Each company's DynamoDB table is independent—no cross-company deduplication needed

### 5. Notify Phase

**Responsibility**: Send consolidated Telegram digest

**Format** (HTML):
```
🚨 {N} New {Company} SDE Role(s)!

1. **Job Title**
   📍 Location
   🏢 Team
   📅 Posted Date
   🔗 Apply

2. ...
```

**Bot Configuration**:
- Each company uses its own bot token
- All bots post to the same channel (shared `TelegramChatId`)

**Error Handling**: If notification fails, log but don't crash

## Extensibility

### Adding a New Company

To add Google, Meta, or Apple:

1. **Create Lambda directory**: `lambdas/{company}/`
2. **Implement scraper**: Follow the 5-phase lifecycle
3. **Add SAM resources**: Copy-paste template pattern from existing company
4. **Update parameters**: Add `TelegramBotToken{Company}` parameter
5. **Deploy**: `sam build && sam deploy`

### Common Patterns Across Companies

| Phase      | Amazon                          | Microsoft                       | Future (Google/Meta/Apple)      |
|------------|----------------------------------|----------------------------------|---------------------------------|
| Pagination | Single request (limit=100)       | `start` parameter loop           | TBD (API-specific)              |
| Timestamp  | String date (`"January 1, 2024"`)| Unix timestamp (`postedTs`)      | TBD (normalize to Unix)         |
| Location   | `country_code` + `location`      | `standardizedLocations` array    | TBD (normalize to string)       |
| Job ID     | `id_icims` or `id`               | `displayJobId`                   | TBD (use native API ID)         |

## Testing Strategy

### Local Testing with SAM CLI

```bash
# Test a specific company scraper
sam local invoke {Company}JobsFunction

# Example: Test Microsoft
sam local invoke MicrosoftJobsFunction
```

### Observability

1. **CloudWatch Logs**: All `print()` statements go to CloudWatch
2. **CloudWatch Alarms**: Trigger on Lambda errors
3. **Telegram Error Notifications**: Unhandled exceptions sent to channel
4. **DynamoDB Metrics**: Track read/write capacity

### Debugging Checklist

When a scraper fails:

1. **Check CloudWatch Logs**: Look for `[ERROR]` or `[SKIP]` messages
2. **Verify API Response**: Log raw API response to inspect schema changes
3. **Test Filters**: Temporarily disable filters to see all jobs
4. **Check DynamoDB**: Scan table to verify deduplication logic
5. **Test Telegram**: Send test message to verify bot token/chat ID

## Design Principles

1. **Idempotency**: Running the same scraper twice should not send duplicate notifications
2. **Fail-Safe**: One company's failure should not affect others
3. **Observability**: Log every decision (fetch, filter, skip, notify)
4. **Cost-Efficiency**: Use pay-per-request billing, ARM64 architecture, and TTL for auto-cleanup
5. **Modularity**: Each company is a standalone Lambda with zero shared code
6. **Isolation**: Each company has its own DynamoDB table and bot token

## Polling Schedule

All scrapers follow the same schedule:

- **Business Hours** (Mon-Fri 7AM-8PM EST): Every 15 minutes
- **Off-Hours** (all other times): Every 30 minutes

This balances responsiveness during peak job posting times with cost efficiency during off-hours.

## Future Enhancements

See `product-roadmap.md` for planned features:
- Shared scraper base class (Strategy Pattern refactor)
- Configurable filters (location, job level, keywords)
- Multi-channel support (Slack, Discord, email)
- Job analytics dashboard
- API rate limit handling with exponential backoff
