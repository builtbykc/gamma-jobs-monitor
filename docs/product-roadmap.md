# Product Roadmap

## Vision

Build a comprehensive, production-grade job monitoring system that tracks Software Development Engineer roles across all major tech companies (GAMMA: Google, Apple, Meta, Microsoft, Amazon) with real-time Telegram notifications, zero maintenance, and near-zero cost.

---

## Current Status (Phase 1: Foundation)

### ✅ Completed
- **Amazon Monitor**: Fully functional Lambda with DynamoDB deduplication
- **Infrastructure**: AWS SAM template with EventBridge schedules
- **Notification**: Telegram bot integration with HTML formatting
- **Observability**: CloudWatch logs and error alarms

### 🚧 In Progress
- **Microsoft Monitor**: Lambda deployed but experiencing failures (see `fix-microsoft-monitor` spec)

### 📋 Pending
- Google, Meta, Apple monitors

---

## Phase 2: Microsoft Stabilization (Current Focus)

**Goal**: Achieve functional parity between Microsoft and Amazon monitors

### Key Deliverables

1. **Fix Microsoft API Integration**
   - Debug pagination issues
   - Validate timestamp filtering (Unix vs string dates)
   - Verify location filtering for USA jobs
   - Test SDE title regex matching

2. **Enhanced Observability**
   - Add detailed logging for each filter stage
   - Log raw API responses for debugging
   - Track filter pass/fail rates
   - Monitor API response times

3. **Discovery & Debug Plan**
   - Create diagnostic Lambda version with verbose logging
   - Test locally with `sam local invoke`
   - Compare Microsoft API response structure to Amazon
   - Document API quirks and edge cases

### Success Criteria
- Microsoft monitor runs without errors for 7 consecutive days
- Notification rate matches expected job posting frequency
- Zero false positives (non-SDE or non-USA jobs)
- Zero false negatives (missed SDE jobs posted in last 24h)

---

## Phase 3: Architecture Refactor (Strategy Pattern)

**Goal**: Eliminate code duplication and establish a scalable foundation for adding Google, Meta, and Apple

### Key Deliverables

1. **Base Scraper Class**
   ```python
   class BaseScraper(ABC):
       """Abstract base class for all company job scrapers."""
       
       @abstractmethod
       def fetch_jobs(self) -> list[dict]:
           """Fetch raw jobs from company API (company-specific pagination)."""
           pass
       
       @abstractmethod
       def normalize(self, job: dict) -> dict:
           """Map company API response to standard Job schema."""
           pass
       
       def is_sde_role(self, title: str) -> bool:
           """Shared SDE title filter (regex-based)."""
           pass
       
       def is_usa_job(self, location: str) -> bool:
           """Shared USA location filter."""
           pass
       
       def is_within_24hrs(self, posted_ts: int) -> bool:
           """Shared freshness filter (24-hour window)."""
           pass
       
       def run(self) -> dict:
           """Main execution flow (fetch → normalize → filter → dedupe → notify)."""
           pass
   ```

2. **Company-Specific Implementations**
   - `AmazonScraper(BaseScraper)`
   - `MicrosoftScraper(BaseScraper)`
   - Future: `GoogleScraper`, `MetaScraper`, `AppleScraper`

3. **Shared Utilities Module**
   - `telegram.py`: Telegram notification helpers
   - `dynamodb.py`: DynamoDB deduplication helpers
   - `filters.py`: Shared filter logic

4. **Lambda Handler Simplification**
   ```python
   # Before (100+ lines per Lambda)
   def lambda_handler(event, context):
       jobs = fetch_jobs()
       for job in jobs:
           # ... 50 lines of filtering/deduplication logic
   
   # After (5 lines per Lambda)
   def lambda_handler(event, context):
       scraper = MicrosoftScraper()
       return scraper.run()
   ```

### Benefits
- **DRY Principle**: Shared logic in base class (filters, deduplication, notifications)
- **Testability**: Unit test base class once, not per company
- **Maintainability**: Bug fixes in base class propagate to all scrapers
- **Extensibility**: New company = implement 2 methods (`fetch_jobs`, `normalize`)

### Migration Strategy
1. Create `lambdas/shared/` directory with base classes
2. Refactor Amazon monitor first (reference implementation)
3. Refactor Microsoft monitor second (validate pattern)
4. Update SAM template to include shared layer
5. Deploy and verify both monitors still work

---

## Phase 4: Google Integration

**Goal**: Add Google Careers API monitoring

### Discovery Tasks

1. **API Research**
   - Identify Google Careers API endpoint
   - Document authentication requirements (if any)
   - Map API response schema to standard Job schema
   - Test pagination mechanism

2. **Filter Calibration**
   - Validate SDE title regex against Google job titles
   - Identify location field format (country code vs full name)
   - Determine timestamp format (Unix vs ISO 8601 vs custom)

3. **Implementation**
   - Create `lambdas/google/lambda_function.py`
   - Implement `GoogleScraper(BaseScraper)`
   - Add SAM resources (Lambda, DynamoDB, EventBridge, CloudWatch)
   - Create Telegram bot token parameter

### Estimated Effort
- API discovery: 2-4 hours
- Implementation: 4-6 hours
- Testing & debugging: 2-4 hours
- **Total**: 8-14 hours

---

## Phase 5: Meta Integration

**Goal**: Add Meta Careers API monitoring

### Discovery Tasks

1. **API Research**
   - Identify Meta Careers API endpoint (likely `https://www.metacareers.com/`)
   - Document API structure and pagination
   - Map response schema to standard Job schema

2. **Filter Calibration**
   - Test SDE title regex (Meta uses "Software Engineer" heavily)
   - Identify location filtering approach
   - Determine timestamp format

3. **Implementation**
   - Create `lambdas/meta/lambda_function.py`
   - Implement `MetaScraper(BaseScraper)`
   - Add SAM resources

### Estimated Effort
- API discovery: 2-4 hours
- Implementation: 4-6 hours
- Testing & debugging: 2-4 hours
- **Total**: 8-14 hours

---

## Phase 6: Apple Integration

**Goal**: Add Apple Careers API monitoring

### Discovery Tasks

1. **API Research**
   - Identify Apple Careers API endpoint (likely `https://jobs.apple.com/`)
   - Document API structure and pagination
   - Map response schema to standard Job schema

2. **Filter Calibration**
   - Test SDE title regex against Apple job titles
   - Identify location filtering approach
   - Determine timestamp format

3. **Implementation**
   - Create `lambdas/apple/lambda_function.py`
   - Implement `AppleScraper(BaseScraper)`
   - Add SAM resources

### Estimated Effort
- API discovery: 2-4 hours
- Implementation: 4-6 hours
- Testing & debugging: 2-4 hours
- **Total**: 8-14 hours

---

## Phase 7: Advanced Features

### Configurable Filters

**Goal**: Allow users to customize job search criteria without code changes

**Features**:
- Location filter (USA, India, UK, Remote, etc.)
- Job level filter (Entry-level, Mid-level, Senior, Staff+)
- Keyword filter (e.g., "Machine Learning", "Backend", "Frontend")
- Exclude filter (e.g., exclude "Intern", "Contractor")

**Implementation**:
- Store filter config in DynamoDB or S3
- Add Lambda environment variables for quick overrides
- Create admin Telegram bot commands (e.g., `/filter location USA,Remote`)

### Multi-Channel Support

**Goal**: Send notifications to Slack, Discord, email, or webhooks

**Features**:
- Slack webhook integration
- Discord webhook integration
- Email via AWS SES
- Generic webhook for custom integrations

**Implementation**:
- Abstract notification layer in base class
- Add channel-specific formatters
- Support multiple channels simultaneously

### Job Analytics Dashboard

**Goal**: Visualize job posting trends over time

**Features**:
- Daily job count by company
- Most common job titles
- Location distribution
- Posting time heatmap

**Implementation**:
- Store job metadata in DynamoDB (already done via TTL items)
- Create Lambda to aggregate metrics
- Use AWS QuickSight or custom dashboard

### Rate Limit Handling

**Goal**: Gracefully handle API rate limits with exponential backoff

**Features**:
- Detect 429 (Too Many Requests) responses
- Implement exponential backoff with jitter
- Queue failed requests for retry
- Alert on persistent rate limit issues

**Implementation**:
- Add retry logic to base scraper class
- Use AWS SQS for retry queue
- Monitor retry rates in CloudWatch

---

## Common Patterns Across Future Integrations

### API Discovery Checklist

For each new company (Google, Meta, Apple):

1. **Find the API endpoint**
   - Check browser DevTools Network tab on careers page
   - Look for JSON responses with job listings
   - Document base URL and query parameters

2. **Understand pagination**
   - Offset-based (`start`, `offset`, `page`)
   - Cursor-based (`next_token`, `cursor`)
   - Page-based (`page=1`, `page=2`)

3. **Map response schema**
   - Job ID field name
   - Title field name
   - Location field (string, array, object?)
   - Posted date field (Unix timestamp, ISO 8601, custom format?)
   - Team/department field name
   - Application URL (absolute or relative?)

4. **Test filters**
   - Run SDE regex against sample job titles
   - Verify location filtering logic
   - Validate timestamp parsing and freshness calculation

5. **Handle edge cases**
   - Missing fields (use `N/A` defaults)
   - Malformed timestamps (skip job or use fallback)
   - Empty location arrays (skip job or use "Remote")
   - Duplicate job IDs (DynamoDB handles this)

### Timestamp Normalization

Different companies use different timestamp formats:

| Company   | Format                     | Normalization                                      |
|-----------|----------------------------|----------------------------------------------------|
| Amazon    | `"January 1, 2024"`        | `datetime.strptime(date_str, "%B %d, %Y")`        |
| Microsoft | `1704067200` (Unix)        | Already Unix timestamp (no conversion needed)      |
| Google    | TBD                        | Discover during API research                       |
| Meta      | TBD                        | Discover during API research                       |
| Apple     | TBD                        | Discover during API research                       |

**Best Practice**: Always normalize to Unix timestamp (seconds since epoch) in the `normalize()` method.

### Location Normalization

Different companies format locations differently:

| Company   | Format                                  | Normalization                          |
|-----------|-----------------------------------------|----------------------------------------|
| Amazon    | `"Seattle, WA, USA"`                    | Check for `, US` or `country_code`     |
| Microsoft | `["United States - Washington"]`        | Join array, check for `United States`  |
| Google    | TBD                                     | Discover during API research           |
| Meta      | TBD                                     | Discover during API research           |
| Apple     | TBD                                     | Discover during API research           |

**Best Practice**: Normalize to a single string in `normalize()`, then apply USA filter in `is_usa_job()`.

---

## Success Metrics

### Phase 2 (Microsoft Stabilization)
- ✅ Zero Lambda errors for 7 consecutive days
- ✅ 100% uptime on EventBridge schedules
- ✅ Notification latency < 30 minutes from job posting

### Phase 3 (Strategy Pattern Refactor)
- ✅ Code duplication reduced by >70%
- ✅ Unit test coverage >80% for base class
- ✅ New company integration time < 8 hours

### Phase 4-6 (Google, Meta, Apple)
- ✅ All 5 companies monitored (GAMMA complete)
- ✅ Combined notification rate: 10-50 jobs/day
- ✅ False positive rate < 5%

### Phase 7 (Advanced Features)
- ✅ User-configurable filters via Telegram bot
- ✅ Multi-channel support (Telegram + Slack + Discord)
- ✅ Analytics dashboard with 30-day trend data

---

## Risk Mitigation

### API Changes
- **Risk**: Company changes API schema or blocks scrapers
- **Mitigation**: 
  - Monitor CloudWatch alarms for sudden error spikes
  - Log raw API responses for debugging
  - Implement graceful degradation (skip company if API fails)

### Rate Limiting
- **Risk**: API rate limits cause missed jobs
- **Mitigation**:
  - Implement exponential backoff
  - Reduce polling frequency if rate limited
  - Use multiple IP addresses (Lambda auto-rotates)

### Cost Overruns
- **Risk**: Unexpected AWS charges
- **Mitigation**:
  - Set CloudWatch billing alarms
  - Use pay-per-request DynamoDB (no provisioned capacity)
  - Monitor Lambda invocation counts

### False Positives
- **Risk**: Non-SDE jobs trigger notifications
- **Mitigation**:
  - Continuously refine SDE regex pattern
  - Add negative filters (exclude "Intern", "Manager", etc.)
  - Allow users to report false positives

---

## Timeline

| Phase | Duration | Target Completion |
|-------|----------|-------------------|
| Phase 2: Microsoft Stabilization | 1-2 weeks | Q2 2026 |
| Phase 3: Strategy Pattern Refactor | 2-3 weeks | Q2 2026 |
| Phase 4: Google Integration | 1-2 weeks | Q3 2026 |
| Phase 5: Meta Integration | 1-2 weeks | Q3 2026 |
| Phase 6: Apple Integration | 1-2 weeks | Q3 2026 |
| Phase 7: Advanced Features | 4-6 weeks | Q4 2026 |

**Total Estimated Timeline**: 3-6 months to full GAMMA coverage with advanced features

---

## Next Steps

1. **Immediate**: Complete `fix-microsoft-monitor` spec and stabilize Microsoft Lambda
2. **Short-term**: Begin Strategy Pattern refactor (Phase 3)
3. **Medium-term**: Add Google, Meta, Apple monitors (Phases 4-6)
4. **Long-term**: Implement advanced features (Phase 7)

---

## Appendix: API Discovery Resources

### Tools
- **Browser DevTools**: Network tab to inspect API calls
- **Postman**: Test API endpoints manually
- **curl**: Command-line API testing
- **jq**: Parse JSON responses

### Example Discovery Process

```bash
# 1. Visit company careers page in browser
open https://www.metacareers.com/jobs

# 2. Open DevTools → Network tab → Filter by "Fetch/XHR"
# 3. Search for jobs → Look for API calls
# 4. Copy API URL and test with curl

curl 'https://www.metacareers.com/api/jobs' \
  -H 'User-Agent: Mozilla/5.0...' \
  | jq '.'

# 5. Document response schema
# 6. Test pagination parameters
# 7. Implement in Python
```

### Common API Patterns

Most careers APIs follow these patterns:

1. **Search Endpoint**: `/api/search`, `/api/jobs`, `/api/positions`
2. **Query Parameters**: `q`, `query`, `keyword`, `search`
3. **Location Filter**: `location`, `country`, `region`
4. **Pagination**: `start`, `offset`, `page`, `limit`, `cursor`
5. **Sorting**: `sort`, `order_by`, `sort_by`

---

## Feedback & Iteration

This roadmap is a living document. As we learn from each integration:

- Update common patterns section
- Refine API discovery checklist
- Adjust timeline estimates
- Add new features based on user feedback

**Last Updated**: May 10, 2026
