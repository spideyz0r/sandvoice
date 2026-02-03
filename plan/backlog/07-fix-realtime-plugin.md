# Fix Realtime Plugin with DuckDuckGo

**Status**: 📋 Planned
**Priority**: 7
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

The realtime plugin is currently broken because it uses the `googlesearch` library, which is unreliable due to Google aggressively blocking automated searches. Replace it with DuckDuckGo search using the `duckduckgo-search` library, which is free, doesn't require an API key, and works reliably.

---

## Problem Statement

**Current situation:**
- Realtime plugin uses `googlesearch.search()` to fetch web search results
- Google blocks automated searches, causing frequent failures
- Users get "I couldn't find any search results" errors
- The `realtime` route (for queries like "Bitcoin price", "Lakers score") is unreliable

**User impact:**
- Voice assistant can't answer current/real-time questions
- One of the core features (web search) is non-functional
- Bad user experience with unpredictable failures

---

## User Stories

**As a user**, I want to ask real-time questions like "What's the Bitcoin price?" and get reliable answers, so I can use the voice assistant for current information.

**As a user**, I want the realtime plugin to work consistently without random failures, so I can trust the assistant for time-sensitive queries.

**As a developer**, I want a free, reliable search backend that doesn't require API keys or rate limit management, so the plugin is maintainable and cost-effective.

---

## Acceptance Criteria

### Search Backend
- [ ] Replace `googlesearch` with `duckduckgo-search` library
- [ ] No API keys required
- [ ] Works reliably without rate limiting
- [ ] Returns 3-5 search results per query (configurable via `search_sources`)

### Functionality
- [ ] Existing behavior preserved (search → extract → summarize → answer)
- [ ] Error handling for network failures
- [ ] Debug logging shows search queries and results
- [ ] Works on both macOS and Raspberry Pi

### User Experience
- [ ] Real-time queries work reliably
- [ ] Response time similar to current implementation
- [ ] Clear error messages if search fails
- [ ] No changes to routes.yaml or user-facing behavior

---

## Technical Requirements

### Library Change

**Remove:**
```python
import googlesearch
results = googlesearch.search(query, num_results=self.num_results)
```

**Replace with:**
```python
from duckduckgo_search import DDGS
results = DDGS().text(query, max_results=self.num_results)
```

### Code Changes

**File**: `plugins/realtime.py`

1. Update imports
2. Replace `GoogleSearcher` class with `DuckDuckGoSearcher`
3. Parse DuckDuckGo result format (dict with 'href', 'title', 'body')
4. Extract URLs from results
5. Keep existing web scraping and summarization logic

### Result Format Difference

**Google search** returns: `['url1', 'url2', 'url3']` (list of strings)

**DuckDuckGo** returns:
```python
[
  {'href': 'url1', 'title': 'Title 1', 'body': 'Snippet 1'},
  {'href': 'url2', 'title': 'Title 2', 'body': 'Snippet 2'}
]
```

Need to extract `href` values.

---

## Configuration Changes

**Update `requirements.txt`:**

Remove:
```
googlesearch_python
```

Add:
```
duckduckgo-search>=4.0.0
```

No changes needed to `config.yaml` - existing `search_sources` setting still applies.

---

## Testing Requirements

### Unit Tests

Create `tests/test_realtime_plugin.py`:
- [ ] Mock DuckDuckGo search results
- [ ] Test URL extraction from DuckDuckGo format
- [ ] Test error handling for empty results
- [ ] Test error handling for network failures
- [ ] Verify existing web scraping logic unchanged

### Integration Tests

- [ ] Test with real DuckDuckGo searches (optional, can be slow)
- [ ] Verify web text extraction still works
- [ ] Test summarization with real search results
- [ ] Test full pipeline: query → search → extract → summarize → answer

### Manual Testing

Test these queries via `realtime` route:
- [ ] "What is the Bitcoin price today?"
- [ ] "Lakers score tonight"
- [ ] "Weather in Tokyo" (should route to weather, not realtime)
- [ ] "Latest news" (should route to news, not realtime)
- [ ] "Recipe for pizza" (should route to default-route, not realtime)

---

## Implementation Plan

### Phase 1: Update Dependencies
1. Remove `googlesearch_python` from requirements.txt
2. Add `duckduckgo-search>=4.0.0` to requirements.txt
3. Test installation on both macOS and Pi

**Checkpoint**: New dependency installs successfully

### Phase 2: Refactor Searcher Class
1. Rename `GoogleSearcher` to `DuckDuckGoSearcher`
2. Update `search()` method to use DDGS
3. Extract URLs from DuckDuckGo result format
4. Add error handling for DuckDuckGo failures
5. Keep debug logging

**Checkpoint**: Search returns URLs correctly

### Phase 3: Testing
1. Write unit tests with mocked DDGS
2. Test with real queries manually
3. Verify error handling
4. Test on Raspberry Pi

**Checkpoint**: All tests pass, realtime queries work

### Phase 4: Documentation
1. Update plugin docstring (if exists)
2. Add comment explaining DuckDuckGo usage
3. Document any limitations

**Checkpoint**: Code is documented

---

## Dependencies

- **Depends on**: None (can be implemented independently)
- **New dependency**: `duckduckgo-search>=4.0.0`

---

## Out of Scope

- Switching to paid search APIs (SerpAPI, Brave Search)
- Adding multiple search backend options
- Implementing OpenAI function calling
- Switching to Perplexity AI
- Adding search result caching
- Parallel search across multiple providers
- Adding search result ranking/filtering

These can be considered in future enhancements if needed.

---

## Success Metrics

- [ ] Realtime plugin works reliably (>95% success rate)
- [ ] No API key management required
- [ ] Search response time <3 seconds
- [ ] Zero cost for search queries
- [ ] Works on both Mac M1 and Raspberry Pi 3B
- [ ] No rate limiting issues

---

## Risk Mitigation

1. **DuckDuckGo blocks us**: Unlikely - they're search-engine friendly. Fallback: use Brave Search API
2. **Result format changes**: Pin version in requirements.txt, add defensive parsing
3. **Network issues**: Already have error handling, will be preserved
4. **Performance**: DuckDuckGo is fast, shouldn't be slower than Google

---

## Alternative Considered

### SerpAPI
- **Pro**: Very reliable, rich results
- **Con**: Costs money ($50/mo for 5k searches)
- **Decision**: Not needed for personal project

### Brave Search API
- **Pro**: Free tier (2k queries/month), good results
- **Con**: Requires API key management
- **Decision**: Keep as backup option if DuckDuckGo fails

### OpenAI Function Calling
- **Pro**: Smart integration, GPT decides when to search
- **Con**: Multiple API calls, higher cost, more complex
- **Decision**: Future enhancement, not for this fix

---

## Estimated Effort

- **Planning**: 30 minutes ✅
- **Implementation**: 1-2 hours
- **Testing**: 30 minutes
- **Documentation**: 15 minutes

**Total**: ~2-3 hours

---

## Notes

- DuckDuckGo doesn't require API keys or authentication
- The `duckduckgo-search` library is actively maintained
- This fix preserves all existing functionality - just swaps the search backend
- No changes to routes.yaml or user-facing behavior
