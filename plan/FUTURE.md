# Future Enhancements

This document tracks features planned for future iterations. These are not currently prioritized but represent valuable improvements for SandVoice.

---

## API Cost Management

Track OpenAI API usage (Whisper transcription, GPT completions, TTS) and provide cost estimates. Add configurable limits to prevent unexpected bills. Include daily/monthly usage reports and warnings when approaching budget thresholds.

---

## Conversation History Management

Currently conversation history grows unbounded, which will eventually hit OpenAI token limits and cause failures. Implement smart truncation strategies (keep recent N messages, summarize old conversations) while maintaining context quality.

---

## Code Deduplication

Refactor duplicated code across plugins, particularly:
- Web scraping logic (appears in realtime, hacker-news plugins)
- Text summarization patterns
- HackerNews class duplicated in technical.py
- Similar API calling patterns

Create shared utility functions to reduce maintenance burden and improve consistency.

---

## Timers & Reminders

Enable time-based interactions like "Hey Sandvoice, remind me in 10 minutes to check the oven" or "Set a timer for 5 minutes". Requires background thread for timer management and notification system for alerts.

---

## Music Control

Integration with music services or local playback:
- Spotify API integration for "play my workout playlist"
- Local music library support (MPD, iTunes)
- Basic controls: play, pause, skip, volume
- Natural language queries: "play something upbeat"

---

## Smart Home Integration

Control smart home devices through voice commands:
- Integration with HomeAssistant, Home Bridge, or similar platforms
- Control lights: "turn off living room lights"
- Adjust thermostats: "set temperature to 72 degrees"
- Check device status: "is the garage door closed?"

---

## Calendar Integration

Access calendar information through natural language:
- "What's on my calendar today?"
- "When is my next meeting?"
- "Do I have anything tomorrow afternoon?"
- Support for Google Calendar, iCloud, Outlook APIs

---

## Todo List Management

Manage todo lists and shopping lists:
- "Add milk to shopping list"
- "What's on my todo list?"
- "Mark 'call dentist' as done"
- Integration with existing todo apps (Todoist, Things) or local storage

---

## Multi-User Support

Recognize different users by voice and provide personalized responses:
- Voice fingerprinting/recognition
- Per-user preferences, calendars, todo lists
- "What's on my calendar?" returns different results per user
- Privacy considerations for shared devices

---

## Conversation Memory

Persistent memory of important facts across sessions:
- "My favorite coffee shop is Starbucks on Main Street"
- Later: "Directions to my favorite coffee shop"
- Vector database (e.g., Chroma) for semantic search of past conversations
- Privacy controls for what gets remembered

---

## Notes

These features are intentionally vague at this stage. When prioritized for development, each will get its own detailed planning document following the same format as current priority features.
