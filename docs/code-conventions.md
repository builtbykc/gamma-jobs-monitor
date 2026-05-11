# Code Conventions & AWS Best Practices

## Overview

This document defines coding standards, AWS best practices, and architectural patterns for the GAMMA Jobs Monitor project. All code must follow these conventions to ensure consistency, maintainability, and production-grade quality.

---

## Python Conventions

### General Style

- **PEP 8 Compliance**: Follow [PEP 8](https://pep8.org/) for all Python code
- **Type Hints**: Use type hints for function signatures (Python 3.13+)
- **Docstrings**: Use triple-quoted docstrings for modules and complex functions
- **Line Length**: Max 100 characters (not the PEP 8 default of 79)

### Naming Conventions

```python
# Constants (module-level)
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
MAX_PAGES = 10
SECONDS_24HR = 86400

# Functions (snake_case)
def fetch_jobs() -> list[dict]:
    pass

def is_sde_role(title: str) -> bool:
    pass

# Variables (snake_case)
new_jobs = []
job_id = "12345"
posted_ts = 1234567890

# Classes (PascalCase) - future Strategy Pattern
class AmazonScraper:
    pass
```

### Import Organization

```python
# 1. Standard library
import json
import os
import re
import time

# 2. Third-party packages
import boto3
import requests

# 3. Local modules (when we have them)
from scrapers.base import BaseScraper
```

### Error Handling

```python
# ✅ GOOD: Specific exceptions with logging
try:
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
except requests.Timeout as e:
    print(f"[ERROR] Request timeout: {e}")
    return []
except requests.HTTPError as e:
    print(f"[ERROR] HTTP error {e.response.status_code}: {e}")
    return []

# ❌ BAD: Bare except
try:
    resp = requests.get(url)
except:
    pass
```

---

## AWS Lambda Best Practices

### Environment Variables

```python
# ✅ GOOD: Fail fast if required env vars missing
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]  # Raises KeyError if missing
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# ❌ BAD: Silent failures
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")  # Empty string on missing
```

### Resource Initialization

```python
# ✅ GOOD: Initialize outside handler (reused across invocations)
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(DYNAMODB_TABLE)

def lambda_handler(event, context):
    # Handler logic uses pre-initialized resources
    pass

# ❌ BAD: Initialize inside handler (recreated every invocation)
def lambda_handler(event, context):
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(DYNAMODB_TABLE)
```

### Timeouts

```python
# ✅ GOOD: Always set timeouts for external calls
resp = requests.get(url, timeout=15)
resp = session.get(url, timeout=15)

# ❌ BAD: No timeout (can hang indefinitely)
resp = requests.get(url)
```

### Logging

```python
# ✅ GOOD: Structured logging with context
print(f"[INFO] Fetched {len(jobs)} jobs from {company} API")
print(f"[SKIP] Title mismatch: {title}")
print(f"[ERROR] DynamoDB put error: {e}")

# ❌ BAD: Unstructured logging
print("got jobs")
print(e)
```

**Log Levels**:
- `[INFO]`: Normal operations (fetch count, new jobs, notifications sent)
- `[SKIP]`: Filtered jobs (title mismatch, too old, non-USA, already seen)
- `[ERROR]`: Failures (API errors, DynamoDB errors, Telegram errors)

### Return Values

```python
# ✅ GOOD: Return structured JSON response
return {
    "statusCode": 200,
    "body": json.dumps({
        "new_jobs": len(new_jobs),
        "checked": len(jobs),
    }),
}

# ❌ BAD: Return arbitrary objects
return new_jobs
```

---

## DynamoDB Best Practices

### Table Design

```python
# ✅ GOOD: Single-item lookup (O(1))
def is_seen(job_id: str) -> bool:
    resp = table.get_item(Key={"job_id": job_id})
    return "Item" in resp

# ❌ BAD: Full table scan (O(n))
def is_seen(job_id: str) -> bool:
    resp = table.scan()
    seen_ids = [item["job_id"] for item in resp["Items"]]
    return job_id in seen_ids
```

### TTL Usage

```python
# ✅ GOOD: Set TTL for auto-cleanup
ttl_ts = int(time.time()) + (90 * 24 * 3600)  # 90 days
table.put_item(Item={
    "job_id": job_id,
    "ttl": ttl_ts,  # DynamoDB auto-deletes when ttl < current_time
    # ... other fields
})
```

### Error Handling

```python
# ✅ GOOD: Log and continue on DynamoDB errors
try:
    table.put_item(Item=item)
except Exception as e:
    print(f"[ERROR] DynamoDB put error: {e}")
    # Continue processing other jobs

# ❌ BAD: Crash entire Lambda on single DynamoDB error
table.put_item(Item=item)  # Unhandled exception stops all processing
```

---

## API Integration Patterns

### Pagination

```python
# ✅ GOOD: Paginate with safety limit
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

### User-Agent Headers

```python
# ✅ GOOD: Mimic real browser to avoid bot detection
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://apply.careers.microsoft.com/",
}

# ❌ BAD: Default User-Agent (often blocked)
resp = requests.get(url)
```

### Response Validation

```python
# ✅ GOOD: Validate response structure
resp = requests.get(url, timeout=15)
resp.raise_for_status()
data = resp.json()
jobs = data.get("jobs", [])  # Safe access with default

# ❌ BAD: Assume response structure
resp = requests.get(url)
jobs = resp.json()["jobs"]  # KeyError if "jobs" missing
```

---

## Telegram Integration

### Message Formatting

```python
# ✅ GOOD: HTML formatting with proper escaping
def build_digest(new_jobs: list[dict]) -> str:
    lines = []
    for i, job in enumerate(new_jobs, 1):
        lines.append(
            f"{i}. <b>{job['title']}</b>\n"
            f"   📍 {job['location']}\n"
            f"   🏢 {job['team']}\n"
            f"   🔗 <a href='{job['url']}'>Apply</a>"
        )
    return f"🚨 <b>{len(new_jobs)} New {company} SDE Role(s)!</b>\n\n" + "\n\n".join(lines)

# ❌ BAD: Plain text (no formatting)
return "\n".join([job["title"] for job in new_jobs])
```

### Error Notifications

```python
# ✅ GOOD: Send error to Telegram, then re-raise
try:
    # Main logic
    pass
except Exception as exc:
    error_msg = f"⚠️ <b>gamma-jobs-{company} — Error</b>\n\n<code>{exc}</code>"
    try:
        send_telegram(error_msg)
    except Exception:
        pass  # Don't mask original exception
    raise  # Re-raise for CloudWatch alarm

# ❌ BAD: Swallow exceptions
try:
    # Main logic
    pass
except Exception:
    pass  # Silent failure
```

---

## AWS SAM Template Conventions

### Resource Naming

```yaml
# ✅ GOOD: Consistent naming pattern
Resources:
  AmazonSeenJobsTable:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: gamma-jobs-amazon-seen

  AmazonJobsFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: gamma-jobs-amazon

# ❌ BAD: Inconsistent naming
Resources:
  Table1:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: amazon-table

  Func:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: lambda-amazon
```

### Parameter Management

```yaml
# ✅ GOOD: NoEcho for sensitive parameters
Parameters:
  TelegramBotTokenAmazon:
    Type: String
    NoEcho: true
    Description: "Telegram bot token for Amazon alerts"

# ❌ BAD: Expose secrets in CloudFormation console
Parameters:
  TelegramBotTokenAmazon:
    Type: String
    Description: "Telegram bot token"
```

### EventBridge Schedules

```yaml
# ✅ GOOD: Descriptive schedule names and comments
Events:
  BusinessHoursCheck:
    Type: Schedule
    Properties:
      Schedule: "cron(0/15 12-20 ? * MON-FRI *)"  # 7AM-8PM EST = 12-20 UTC
      Description: "Every 15 min, Mon-Fri 7AM-8PM EST"
      Enabled: true

# ❌ BAD: Unclear schedule names
Events:
  Event1:
    Type: Schedule
    Properties:
      Schedule: "cron(0/15 12-20 ? * MON-FRI *)"
```

---

## Testing Conventions

### Local Testing

```bash
# ✅ GOOD: Test before deploying
sam build
sam local invoke MicrosoftJobsFunction

# ❌ BAD: Deploy without testing
sam build && sam deploy
```

### Manual Invocation

```bash
# ✅ GOOD: Test deployed Lambda
aws lambda invoke \
  --function-name gamma-jobs-microsoft \
  --payload '{}' \
  response.json && cat response.json

# Check logs
sam logs -n gamma-jobs-microsoft --tail
```

---

## Security Best Practices

### Secrets Management

```yaml
# ✅ GOOD: Use SAM parameters (stored in AWS Systems Manager)
Parameters:
  TelegramBotTokenAmazon:
    Type: String
    NoEcho: true

# ❌ BAD: Hardcode secrets
Environment:
  Variables:
    TELEGRAM_BOT_TOKEN: "123456789:ABCdef..."
```

### IAM Permissions

```yaml
# ✅ GOOD: Least-privilege policies
Policies:
  - DynamoDBCrudPolicy:
      TableName: !Ref AmazonSeenJobsTable

# ❌ BAD: Overly permissive
Policies:
  - AmazonDynamoDBFullAccess
```

---

## Performance Optimization

### ARM64 Architecture

```yaml
# ✅ GOOD: Use ARM64 for 20% cost savings
Globals:
  Function:
    Architectures: [arm64]

# ❌ BAD: Default x86_64
Globals:
  Function:
    Architectures: [x86_64]
```

### Memory Sizing

```yaml
# ✅ GOOD: Right-size memory (256 MB sufficient for HTTP + DynamoDB)
Globals:
  Function:
    MemorySize: 256

# ❌ BAD: Over-provision
Globals:
  Function:
    MemorySize: 1024
```

### Connection Reuse

```python
# ✅ GOOD: Reuse session across requests
session = requests.Session()
session.headers.update(HEADERS)

def fetch_jobs():
    resp = session.get(url)  # Reuses TCP connection

# ❌ BAD: Create new connection per request
def fetch_jobs():
    resp = requests.get(url, headers=HEADERS)
```

---

## Monitoring & Observability

### CloudWatch Alarms

```yaml
# ✅ GOOD: Monitor errors with appropriate threshold
AmazonErrorAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    MetricName: Errors
    Threshold: 1
    EvaluationPeriods: 1
    ComparisonOperator: GreaterThanOrEqualToThreshold
```

### Structured Logging

```python
# ✅ GOOD: Log key metrics
print(f"[INFO] Done — {len(new_jobs)} new job(s) out of {len(jobs)} checked")

# ❌ BAD: Vague logging
print("done")
```

---

## Future Strategy Pattern (Post-Refactor)

When implementing the Strategy Pattern refactor:

```python
# Base class (abstract)
class BaseScraper(ABC):
    @abstractmethod
    def fetch_jobs(self) -> list[dict]:
        pass

    @abstractmethod
    def normalize(self, job: dict) -> dict:
        pass

    def is_sde_role(self, title: str) -> bool:
        # Shared implementation
        pass

# Company-specific implementation
class MicrosoftScraper(BaseScraper):
    def fetch_jobs(self) -> list[dict]:
        # Microsoft-specific pagination
        pass

    def normalize(self, job: dict) -> dict:
        # Microsoft-specific field mapping
        pass
```

---

## Code Review Checklist

Before merging any code:

- [ ] Type hints on all function signatures
- [ ] Timeouts on all external HTTP calls
- [ ] Error handling with structured logging
- [ ] DynamoDB operations use `get_item` (not `scan`)
- [ ] TTL set on all DynamoDB writes
- [ ] Telegram messages use HTML formatting
- [ ] SAM template uses ARM64 architecture
- [ ] Secrets use `NoEcho: true` in parameters
- [ ] CloudWatch alarms configured for new Lambdas
- [ ] Local testing with `sam local invoke` passes
- [ ] No hardcoded secrets or credentials
- [ ] Pagination has safety limits (MAX_PAGES)
- [ ] User-Agent headers set for API calls
- [ ] Return structured JSON from Lambda handler

---

## References

- [AWS Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [AWS SAM Developer Guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html)
- [DynamoDB Best Practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/best-practices.html)
- [PEP 8 Style Guide](https://pep8.org/)
- [Python Type Hints](https://docs.python.org/3/library/typing.html)
