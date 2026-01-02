# UI Improvements Summary

## 1. Add Project Tab - URL Parsing

### Before:
- Manual site selection from dropdown
- Manual project ID entry
- No URL parsing

### After:
- **Primary input: "Vote Link URL"** field at top
- Paste URL like `https://minecraft-server.eu/vote/index/208F7/`
- Auto-detects:
  - Provider: minecraft-server.eu
  - Project ID: 208F7
- Provider dropdown and Project ID fields auto-fill
- Clear error messages if parsing fails
- Supports 9+ sites with validation

### Visual Changes:
```
┌─────────────────────────────────────────┐
│ Vote Link URL *                         │
│ ┌─────────────────────────────────────┐ │
│ │ Paste vote URL here...              │ │
│ └─────────────────────────────────────┘ │
│ ℹ️ Paste a vote URL and we'll auto-    │
│    detect the site and project ID      │
├─────────────────────────────────────────┤
│ Rating Site * (auto-filled)             │
│ [minecraft-server.eu ▼]                 │
├─────────────────────────────────────────┤
│ Project ID * (auto-filled)              │
│ [208F7]                                 │
└─────────────────────────────────────────┘
```

## 2. Settings Tab - Debug Mode Grouping

### Before:
- Debug checkbox separate from actions
- No helper text
- Users confused about relationship

### After:
- **Grouped in bordered section**
- Toggle and Download button side-by-side
- Clear section heading: "Debug Mode"
- Helper text: "Enable verbose logs and diagnostic overlays for troubleshooting"
- Consistent styling with blue accent

### Visual Changes:
```
┌───────────────────────────────────────────┐
│ ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓ │
│ ┃ Debug Mode                          ┃ │
│ ┃ ┌─────────────────┬───────────────┐ ┃ │
│ ┃ │ ☑ Enable Debug │ Download Logs │ ┃ │
│ ┃ └─────────────────┴───────────────┘ ┃ │
│ ┃ ℹ️ Enable verbose logs and         ┃ │
│ ┃    diagnostic overlays for         ┃ │
│ ┃    troubleshooting                 ┃ │
│ ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛ │
└───────────────────────────────────────────┘
```

## 3. Settings Tab - New Scheduling Options

### Added Sections:
1. **Scheduling**
   - Daily Window - Earliest Time: [09:00]
   - Daily Window - Latest Time: [21:00]
   - ☑ Enable Same-Day Retries
   - Max Retries Per Day: [3]

2. **Timeouts**
   - Page Load Timeout (ms): [5000]
   - Error Retry Delay (ms): [900000]

### Features:
- Time pickers for daily window
- Checkbox to enable/disable retries
- Number input for max retries
- Helper text for each setting

## 4. Backend Enhancements

### Flexible Scheduling Logic:
```python
# Next-day scheduling
- Random hour in [earliest, latest]
- Random minute [0-59]
- ±10 minute jitter
- Always within configured window

# Same-day retry
- Exponential backoff: 30m, 1h, 2h...
- ±20% jitter
- Stops at max retries or window end
- Resets counter at midnight
```

### State Tracking:
```json
{
  "lastAttemptAt": 1704067200000,
  "lastSuccessAt": 1704067200000,
  "nextAttemptAt": 1704153600000,
  "retriesTodayCount": 0,
  "lastError": null
}
```

## 5. Vote Reminder Mode

### Implementation:
- Opens vote page in browser
- Waits 5 seconds (user sees page)
- Logs: "USER MUST COMPLETE VOTE MANUALLY"
- NO auto-clicking or form submission
- Compliant with terms of service

### Headless Recommendation:
Set `HEADLESS=false` in docker-compose.yml for reminder mode:
```yaml
environment:
  - HEADLESS=false
```

## Testing the UI

1. Start container: `docker-compose up -d`
2. Open: `http://localhost:8080`
3. Navigate to "Add Project" tab
4. Paste: `https://minecraft-server.eu/vote/index/208F7/`
5. Watch auto-fill happen
6. Navigate to "Settings" tab
7. See grouped Debug Mode section
8. See new Scheduling options

## Summary of Changes

| Feature | Status | Lines Changed |
|---------|--------|---------------|
| URL Parsing | ✅ | ~100 (JS) |
| Debug Grouping | ✅ | ~20 (HTML) |
| Flexible Scheduling | ✅ | ~80 (Python) |
| Retry Logic | ✅ | ~60 (Python) |
| State Tracking | ✅ | ~30 (Python) |
| Reminder Mode | ✅ | ~40 (Python) |
| Logs Download | ✅ | ~15 (Python) |

**Total**: ~345 lines of meaningful code changes
