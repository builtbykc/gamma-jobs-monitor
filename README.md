# GAMMA Jobs Monitor 🚨

Polls **Amazon Jobs** for new SDE roles in the USA and fires instant **Telegram notifications** — serverless, zero-maintenance, near-zero cost.

> Currently monitors Amazon. Microsoft, Google, Meta, and Apple support coming soon.

---

## How It Works

```
EventBridge (3 schedules)
  ├─ every 15 min  — weekdays, 7AM–6PM EST
  ├─ every 30 min  — weekdays, off-hours
  └─ every 30 min  — weekends
        │
        ▼
  Lambda (Python 3.13, arm64)
        ├─► Amazon Jobs API  — fetch latest SDE roles (USA, last 24h)
        ├─► DynamoDB         — deduplicate via job ID (TTL: 90 days)
        └─► Telegram Bot     — send digest of new roles
```

---

## Prerequisites

| Tool | Version |
|---|---|
| [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) | v2 |
| [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) | latest |
| Python | 3.13 |

---

## Setup

### 1. Create a Telegram Bot

1. Message **@BotFather** on Telegram → `/newbot`
2. Copy the **Bot Token** (`123456789:ABCdef...`)
3. Get your **Chat ID** — send a message to your bot, then visit:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
   Copy `result[0].message.chat.id`

### 2. Configure AWS credentials

```bash
aws configure
# Access Key ID, Secret Access Key, region (e.g. us-east-2), output: json
```

### 3. Deploy

```bash
git clone https://github.com/your-username/gamma-jobs-monitor
cd gamma-jobs-monitor

sam build

sam deploy --guided
# Stack name:           gamma-jobs-monitor
# Region:               us-east-2
# TelegramBotTokenAmazon: <your bot token>
# TelegramChatId:       <your chat ID>
# Allow SAM IAM roles:  y
# Save to samconfig.toml: y
```

Future deploys:
```bash
sam build && sam deploy
```

---

## Test Manually

```bash
aws lambda invoke \
  --function-name gamma-jobs-amazon \
  --payload '{}' \
  response.json && cat response.json
```

---

## Useful Commands

```bash
# Tail live logs
sam logs -n gamma-jobs-amazon --tail

# Inspect seen jobs in DynamoDB
aws dynamodb scan \
  --table-name gamma-jobs-amazon-seen \
  --query "Items[*].{ID:job_id.S,Title:title.S}"

# Tear everything down
sam delete
```

---

## Customise the Search

Edit `SEARCH_PARAMS` in `lambdas/amazon/lambda_function.py`:

```python
"base_query":                "Software Development Engineer"
"normalized_country_code[]": "USA"   # change to "IND", "GBR", etc.
"result_limit":              100
```

---

## Cost

All within AWS free tier for typical usage.

| Service | Est. monthly invocations | Cost |
|---|---|---|
| Lambda | ~1,400 | ~$0.00 |
| DynamoDB | ~100 writes | ~$0.00 |
| EventBridge | ~1,400 events | ~$0.00 |


