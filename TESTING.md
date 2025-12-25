# Testing Guide for Auto-Vote-Rating Docker

This guide helps you test the Docker implementation of Auto-Vote-Rating.

## Pre-Testing Checklist

- [ ] Docker installed (version 20.10+)
- [ ] Docker Compose installed (version 1.29+)
- [ ] At least 2GB free disk space
- [ ] Port 8080 available

## Quick Test

### 1. Build and Start

```bash
# Clone the repository
git clone https://github.com/cancel-cloud/Auto-Vote-Rating.git
cd Auto-Vote-Rating

# Build and start
docker-compose up -d

# Check logs
docker-compose logs -f
```

**Expected output:**
- Container builds successfully
- Worker starts and initializes database
- Dashboard starts on port 8080
- No error messages in logs

### 2. Access Dashboard

1. Open browser: `http://localhost:8080`
2. You should see the dashboard with 4 tabs:
   - Projects
   - Add Project
   - Settings
   - Statistics

**Test:** Can you see the dashboard? ✅ / ❌

### 3. Add a Test Project

1. Click "Add Project" tab
2. Fill in:
   - Rating Site: `minecraftservers.org`
   - Project ID: `25531` (example)
   - Nickname: `TestUser`
   - Project Name: `Test Server`
3. Click "Add Project"

**Expected:**
- Success notification appears
- Redirected to Projects tab
- Project appears in the list
- "Next Vote: Soon" displayed

**Test:** Can you add a project? ✅ / ❌

### 4. Check Data Persistence

```bash
# Check if data files were created
ls -la data/

# Expected files:
# - projects.json
# - settings.json
# - stats.json
# - worker.log

cat data/projects.json
```

**Expected:** JSON file contains your project

**Test:** Are data files created? ✅ / ❌

### 5. Test Vote Now Feature

1. In Projects tab, click "Vote Now" on your project
2. Wait 30 seconds
3. Refresh the page

**Expected:**
- Project status updates
- Next vote time is set (24 hours from now)
- Statistics increment OR error message appears

**Note:** Some sites may fail due to:
- Invalid project ID
- Captcha required
- Site structure changes

This is expected behavior - the error should be logged.

**Test:** Does "Vote Now" trigger an attempt? ✅ / ❌

### 6. Test Statistics

1. Click "Statistics" tab
2. Check if numbers update after voting

**Expected:**
- Total votes counter
- Today's votes
- Error count (if voting failed)

**Test:** Do statistics update? ✅ / ❌

### 7. Test Settings

1. Click "Settings" tab
2. Change timeout value
3. Click "Save Settings"
4. Refresh page
5. Settings should persist

**Test:** Do settings save? ✅ / ❌

### 8. Test Delete Project

1. Go to Projects tab
2. Click "Delete" on a project
3. Confirm deletion

**Expected:**
- Project removed from list
- Data file updated

**Test:** Can you delete projects? ✅ / ❌

### 9. Test Container Restart

```bash
# Restart container
docker-compose restart

# Wait 10 seconds
sleep 10

# Check if projects still exist
docker-compose logs
```

**Expected:**
- Container restarts successfully
- Projects load from disk
- Worker resumes checking schedule

**Test:** Do projects persist after restart? ✅ / ❌

### 10. Test Auto-Refresh

1. Open dashboard
2. Wait 30 seconds
3. Projects should auto-refresh

**Expected:**
- Page updates without manual refresh
- Time displays update

**Test:** Does auto-refresh work? ✅ / ❌

## Advanced Testing

### Test Multiple Projects

Add 3-5 different projects with different rating sites:
- Test that each site's URL pattern works
- Test that voting schedules don't conflict
- Test that statistics track separately

### Test Error Handling

Try adding invalid projects:
- Non-existent project IDs
- Invalid rating site
- Empty fields

Expected: Proper error messages

### Test Browser Automation

Check worker logs during voting:

```bash
docker-compose logs -f auto-vote-rating
```

Look for:
- Browser launch messages
- Navigation to voting pages
- Vote attempt logs
- Success or error messages

### Test Resource Usage

```bash
# Check container resources
docker stats auto-vote-rating

# Should be reasonable:
# - CPU: <5% idle, <50% during voting
# - Memory: <500MB
```

### Test Long Running

Leave container running for 24 hours:
- Check if scheduled votes execute
- Check for memory leaks
- Check log file size

## Troubleshooting Tests

### If dashboard doesn't load:

```bash
# Check if container is running
docker ps

# Check port binding
docker port auto-vote-rating

# Check logs for errors
docker-compose logs dashboard
```

### If voting fails:

```bash
# Check worker logs
docker-compose logs worker

# Common issues:
# - Browser not installed
# - Timeout too short
# - Site requires captcha
# - Invalid project ID
```

### If data doesn't persist:

```bash
# Check volume mounting
docker inspect auto-vote-rating | grep -A 10 Mounts

# Check permissions
ls -la data/

# Should be writable by container user
```

## Performance Tests

### Vote Timing Accuracy

1. Add a project
2. Click "Vote Now"
3. Note the "Next Vote" time
4. Wait until that time
5. Check if vote executes within 1 minute of scheduled time

### Concurrent Voting

1. Add 5 projects
2. Set all to vote at same time
3. Check if all complete successfully
4. Check logs for any race conditions

### Dashboard Load Test

1. Add 20+ projects
2. Check if dashboard remains responsive
3. Check if statistics calculate correctly
4. Check memory usage

## Cleanup After Testing

```bash
# Stop container
docker-compose down

# Remove data
rm -rf data/

# Remove images (optional)
docker rmi auto-vote-rating_auto-vote-rating
```

## Test Results Template

Copy and fill out:

```
## Test Results

Date: ___________
Docker Version: ___________
OS: ___________

### Quick Tests
- [ ] Build and Start
- [ ] Access Dashboard
- [ ] Add Project
- [ ] Data Persistence
- [ ] Vote Now
- [ ] Statistics
- [ ] Settings
- [ ] Delete Project
- [ ] Container Restart
- [ ] Auto-Refresh

### Issues Found
1. 
2. 
3. 

### Notes
- 
- 
- 

### Overall: PASS / FAIL
```

## Reporting Issues

If you find bugs, please report with:
1. Test that failed
2. Expected behavior
3. Actual behavior
4. Docker logs
5. System info (OS, Docker version)

Submit to: https://github.com/cancel-cloud/Auto-Vote-Rating/issues
