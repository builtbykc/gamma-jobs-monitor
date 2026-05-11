# Microsoft Jobs Monitor

This directory contains the AWS Lambda function (`gamma-jobs-microsoft`) that polls the Microsoft Careers API for new Software Development Engineer (SDE) roles in the USA.

## Architecture

The monitor follows this high-level data flow:
1. **Fetch**: Paginates through the Microsoft API until all results are retrieved. Implements a polite 1-second delay between requests to avoid rate limiting.
2. **Normalize**: Maps Microsoft API fields to the standard `Job_Record` format.
3. **Filter**: Applies SDE title, USA location, and 24-hour freshness filters.
4. **Deduplicate**: Checks DynamoDB for previously seen jobs to prevent duplicate notifications.
5. **Notify**: Sends a Telegram digest of new jobs.

## Component Details

### Fetcher & Pagination
- **Endpoint**: `https://apply.careers.microsoft.com/api/pcsx/search`
- **Parameters**: `domain: microsoft.com`, `query: software engineer`, `location: United States`, `sort_by: new`, `filter_include_remote: 1`.
- **Headers**: Includes stable headers (`User-Agent`, `Accept`, `Referer`). Explicitly excludes session-specific headers (`x-csrf-token`, `request-id`, etc.) to prevent rapid expiration between Lambda invocations.
- **Pagination Logic**: Increments `start` by the batch length until an empty batch or the total count is reached. Max limit: 10 pages. 1-second delay between pagination requests.

### Data Normalization
- `job_id`: Prefixed with `microsoft_` (e.g., `microsoft_{displayJobId}`).
- `location`: All locations in the `locations` array are joined with `" | "`.
- `posted_ts`: Microsoft API returns Unix timestamps directly (`postedTs`).

### Filters
- **24-hour Freshness**: Age calculated as `current_time - posted_ts`. Must be <= 86400 seconds.
- **Location Filter**: Matches `, US`, `US`, or `United States`.
- **Title Filter**: Regex match for `(software\s+eng[\w]*|SWE|SDE)` (case-insensitive).

### Deduplication (DynamoDB)
- **Table**: `gamma-jobs-microsoft-seen`
- **TTL**: 90 days. Checked using `job_id`.

## Configuration & Deployment

- **Timeout**: The Lambda function timeout is set to 90 seconds to account for pagination and API request delays.
- **Environment Variables**:
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`
  - `DYNAMODB_TABLE`
- **EventBridge Schedules**:
  - *Business Hours*: Every 15 minutes, Mon-Fri 7AM-8PM EST (`cron(0/15 12-20 ? * MON-FRI *)`).
  - *Off-Hours*: Every 30 minutes, all other times (`cron(0/30 * ? * * *)`).

## Local Testing
To test the monitor locally using AWS SAM:
```bash
sam build
sam local invoke MicrosoftJobsFunction
```
