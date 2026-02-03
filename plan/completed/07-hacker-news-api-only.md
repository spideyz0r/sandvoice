# Hacker News: API-Only Summaries (No HTML Parsing)

**Status**: ✅ Completed
**Priority**: 7

---

## Overview

The Hacker News plugin previously fetched `beststories` from the official Hacker News Firebase API, then downloaded and parsed each story's external article URL to generate summaries. This was brittle (sites block requests) and failed when the `lxml` HTML parser dependency wasn't available.

This work updates the Hacker News plugin to use only the free Hacker News Firebase API response fields (title, URL, score, comments, author, timestamp, and optional `text`) while preserving the same "podcast-style" output (takeaways + opinions) without fetching external pages.

---

## Result

- ✅ No external HTML fetch/parsing for Hacker News stories
- ✅ No `lxml` dependency required for the Hacker News plugin
- ✅ Faster + cheaper: avoids downloading and summarizing full article pages
- ✅ Preserves overall output structure and tone (podcast/news report style)

---

## Acceptance Criteria

- [x] `plugins/hacker-news.py` no longer uses `WebTextExtractor` or BeautifulSoup
- [x] The plugin works without `lxml` installed
- [x] Output remains in the same "podcast" style with takeaways and opinions
- [x] In debug mode, logs how many stories were fetched/included
- [x] Maintains existing config knobs (`api_timeout`, `summary_words`, etc.)

---

## Testing

- [x] Unit tests added with mocked Firebase responses and mocked AI
