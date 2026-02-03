# Hacker News: API-Only Summaries (No HTML Parsing)

**Status**: 📋 Backlog
**Priority**: 7

---

## Overview

The current Hacker News plugin fetches `beststories` from the official Hacker News Firebase API, then downloads and parses each story's external article URL to generate summaries. This approach is brittle (sites block requests) and currently fails when the `lxml` HTML parser dependency isn't available.

We should update the Hacker News plugin to use only the free Hacker News Firebase API response fields (title, URL, score, comments, author, timestamp, and optional `text`) to create the same "podcast-style" output (takeaways + opinions) without fetching external pages.

---

## Problem Statement

Current behavior:
- Fetch HN story IDs via Firebase API
- Fetch each story JSON
- Fetch and parse external article HTML (requires BeautifulSoup + `lxml`)
- Summarize external article text with GPT
- Generate final podcast-style response with takeaways/opinion

Issues:
- External URLs frequently block scraping or time out
- `lxml` may not be installed, causing parse failures
- Extra latency and token cost for downloading and summarizing full article text

---

## Goals

- Eliminate dependence on HTML parsing (`lxml`) and external article fetches
- Keep the overall output structure and tone: podcast/news report style, include takeaways and opinions
- Preserve reliability across macOS and Raspberry Pi
- Reduce latency and token usage

---

## Non-Goals

- Building a full HN reader UI
- Guaranteeing deep article comprehension (we will not read full external pages in this plan)
- Changing routing behavior (route name remains `hacker-news`)

---

## Proposed Design

### Data Source

Use only the free Hacker News Firebase API:
- `beststories.json` (or optionally `topstories.json`)
- `item/<id>.json`

### Data Extracted per Story

Collect a compact list of story objects:
- `title`
- `url` (may be missing)
- `score`
- `descendants` (comment count)
- `by`
- `time`
- `text` (optional; some posts)

### Prompt / Output

Continue the existing approach:
- Provide the list of stories as context to GPT
- Ask for a podcast-style summary with:
  - brief context per item (from title + metadata)
  - takeaways per item
  - opinion per item
- Keep "Don't read the URLs" constraint

### Optional Enhancement (Later)

Allow an opt-in mode to fetch and summarize external URLs for *only 1-2* top stories, but only if a safe HTML parser is available or using a non-`lxml` fallback.

---

## Acceptance Criteria

- [ ] `plugins/hacker-news.py` no longer uses `WebTextExtractor` or BeautifulSoup
- [ ] The plugin works without `lxml` installed
- [ ] Output remains in the same "podcast" style with takeaways and opinions
- [ ] In debug mode, logs the story IDs fetched and how many stories were successfully included
- [ ] Maintains existing config knobs (`api_timeout`, `summary_words`, etc.)

---

## Testing

- Unit test: plugin logic builds the story context list correctly with mocked Firebase responses
- Unit test: missing `url` or missing fields are handled gracefully
- Integration smoke test: run the plugin end-to-end with a real API call (optional/manual)
