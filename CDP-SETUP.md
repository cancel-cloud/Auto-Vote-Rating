# CDP (Chrome DevTools Protocol) Manual Captcha Solving Setup

This guide explains how to configure the CDP browser for manual captcha solving in different environments.

## Overview

When the system encounters a captcha it can't solve automatically, it launches a headless Chrome browser with CDP enabled. You can connect to this browser remotely to solve the captcha manually, and then resume automation.

## Browser Lifecycle

1. **Captcha Detected** → System sets status to `NEEDS_USER_ACTION`
2. **Launch Manual Browser** → Click button in dashboard → Browser starts in background and stays alive
3. **Open Browser** → Click the link to access browser via CDP
4. **Solve Captcha** → Complete the captcha manually in the remote browser
5. **Resume Automation** → Click "✓ I Solved It" → Browser closes, automation resumes

**Important**: The browser stays alive until you click "✓ I Solved It - Resume Automation". Don't restart the container or the browser will close.

## Configuration

The CDP browser URL is controlled by the `CDP_PUBLIC_HOST` environment variable.

### Local Development (MacBook, Desktop)

Use `localhost` or `127.0.0.1`:

```bash
# In .env file
CDP_PUBLIC_HOST=localhost
```

Then rebuild:
```bash
docker-compose down && docker-compose up --build -d
```

Access at: `http://localhost:9222`

### Production Deployment (Server)

Use your server's public IP address or domain:

```bash
# In .env file
CDP_PUBLIC_HOST=192.168.1.100
# or
CDP_PUBLIC_HOST=your-server.com
```

Then rebuild:
```bash
docker-compose down && docker-compose up --build -d
```

Access at: `http://192.168.1.100:9222` or `http://your-server.com:9222`

## Step-by-Step Setup

### For Local Development

1. **Copy the example environment file**:
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` file**:
   ```bash
   CDP_PUBLIC_HOST=localhost
   ```

3. **Rebuild and start**:
   ```bash
   docker-compose down && docker-compose up --build -d
   ```

4. **Test**:
   - Open dashboard: http://localhost:8080
   - Trigger a vote that will encounter a captcha
   - Click "Launch Manual Browser"
   - Click "🌐 Open Browser" → Should open http://localhost:9222
   - Solve captcha
   - Click "✓ I Solved It - Resume Automation"

### For Production Deployment

1. **Find your server's IP**:
   ```bash
   # On Linux
   ip addr show | grep inet

   # On Mac
   ifconfig | grep inet
   ```

2. **Create `.env` file on server**:
   ```bash
   echo "CDP_PUBLIC_HOST=YOUR_SERVER_IP" > .env
   ```

3. **Rebuild and start**:
   ```bash
   docker-compose down && docker-compose up --build -d
   ```

4. **Ensure port 9222 is accessible**:
   - Check firewall allows port 9222
   - For cloud servers (AWS, GCP, Azure), ensure security group allows inbound traffic on port 9222

## Troubleshooting

### "This site can't be reached" Error

1. **Check logs**:
   ```bash
   docker logs auto-vote-rating 2>&1 | grep "Background thread"
   ```

   You should see:
   ```
   Background thread: Starting browser launch
   Background thread: Browser launched successfully
   Background thread: User can access at: http://...
   ```

2. **Verify CDP_PUBLIC_HOST**:
   ```bash
   docker logs auto-vote-rating 2>&1 | grep "CDP URL"
   ```

3. **Test port accessibility**:
   ```bash
   # From host machine
   curl http://localhost:9222/json/version

   # From another machine (use server IP)
   curl http://YOUR_SERVER_IP:9222/json/version
   ```

### Browser Closes Immediately

This was fixed in the latest version. The browser now stays alive until you click "✓ I Solved It - Resume Automation".

If it still closes:
- Check logs for errors: `docker logs auto-vote-rating 2>&1 | tail -50`
- Ensure you didn't restart the container (this kills all browsers)

### Can't Access from Remote Machine

1. **Check firewall**:
   ```bash
   # Ubuntu/Debian
   sudo ufw allow 9222

   # CentOS/RHEL
   sudo firewall-cmd --add-port=9222/tcp --permanent
   sudo firewall-cmd --reload
   ```

2. **For cloud servers**, update security groups to allow inbound traffic on port 9222

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `CDP_ENABLED` | `true` | Enable/disable CDP browser |
| `CDP_BASE_PORT` | `9222` | Port for CDP to bind to |
| `CDP_HOST` | `0.0.0.0` | Bind address (don't change) |
| `CDP_PUBLIC_HOST` | `localhost` | **CHANGE THIS**: Public address for browser access |
| `CDP_AUTH_TOKEN` | auto-generated | Optional: Custom auth token |

## Security Notes

1. **Port 9222** gives full browser access - only expose it on trusted networks
2. **CDP_AUTH_TOKEN**: Consider setting a custom token in production
3. **Firewall**: Restrict port 9222 access to specific IPs if possible
4. **HTTPS**: For production, consider using a reverse proxy with HTTPS

## Quick Reference

**Local Development**:
```bash
# .env
CDP_PUBLIC_HOST=localhost
```

**Production**:
```bash
# .env
CDP_PUBLIC_HOST=192.168.1.100
```

**Rebuild**:
```bash
docker-compose down && docker-compose up --build -d
```

**Check Status**:
```bash
docker logs auto-vote-rating --tail 50
```
