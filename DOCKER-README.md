# Auto Vote Rating - Docker Version

A self-hosted Docker container that automates voting on gaming server listing sites. This is a Python-based replacement for the browser extension with the same functionality and a web dashboard.

## Features

- ✅ **Automated Voting**: Votes every 24 hours automatically
- ✅ **Web Dashboard**: Manage projects, view statistics, and configure settings
- ✅ **Persistent Storage**: All data stored in volumes
- ✅ **Same Sites**: Supports all the same voting sites as the browser extension
- ✅ **Easy Deployment**: Single docker-compose command to get started

## Quick Start

### Prerequisites

- Docker
- Docker Compose

### Installation

1. Clone the repository:
```bash
git clone https://github.com/cancel-cloud/Auto-Vote-Rating.git
cd Auto-Vote-Rating
```

2. Start the container:
```bash
docker-compose up -d
```

3. Access the dashboard:
```
http://localhost:8080
```

### First Time Setup

1. Open the dashboard at `http://localhost:8080`
2. Click on "Add Project" tab
3. Fill in the project details:
   - **Rating Site**: Select from the dropdown
   - **Project ID**: Your server/project ID on that site
   - **Nickname**: (Optional) Your Minecraft username
   - **Project Name**: (Optional) Display name
4. Click "Add Project"
5. The worker will automatically start voting every 24 hours

## Configuration

### Environment Variables

Edit `docker-compose.yml` to customize:

```yaml
environment:
  - TZ=UTC                    # Your timezone
  - DASHBOARD_HOST=0.0.0.0   # Dashboard host
  - DASHBOARD_PORT=8080       # Dashboard port
  - DATA_DIR=/app/data        # Data directory
  - HEADLESS=true            # Run browser in headless mode
  - DEBUG=false              # Enable debug logging
```

### Ports

By default, the dashboard runs on port 8080. To change it:

```yaml
ports:
  - "8080:8080"  # Change first 8080 to your desired port
```

### Data Persistence

All data is stored in the `./data` directory:
- `projects.json` - Your configured projects
- `settings.json` - Application settings
- `stats.json` - Voting statistics
- `worker.log` - Worker logs

## Usage

### Managing Projects

**Add a Project:**
1. Go to "Add Project" tab
2. Fill in the form
3. Click "Add Project"

**Vote Now:**
- Click "Vote Now" button on any project to trigger immediate voting

**Delete a Project:**
- Click "Delete" button on the project card

### Viewing Statistics

Go to the "Statistics" tab to view:
- Total successful votes
- Monthly votes
- Today's votes
- Error count

### Settings

Configure various options in the "Settings" tab:
- Debug mode
- Timeout values
- Retry timeouts

## Supported Sites

The Docker version supports the same sites as the browser extension, including:

- topcraft.club / topcraft.ru
- mctop.su
- mcrate.su
- minecraftrating.ru
- minecraftservers.org
- planetminecraft.com
- topg.org
- And many more...

See the [full list](README.md#list-of-sites-that-the-extension-supports) in the main README.

## Architecture

### Components

1. **Worker** (`worker/main.py`)
   - Runs in the background
   - Checks voting schedule every minute
   - Executes votes using Playwright (headless browser)
   - Updates statistics and next vote times

2. **Dashboard** (`dashboard/app.py`)
   - Flask web application
   - REST API for managing projects
   - Web interface for configuration
   - Real-time statistics

3. **Database** (`worker/database.py`)
   - JSON-based storage
   - Projects, settings, and statistics
   - Persistent across container restarts

### How It Works

1. The worker starts and loads all configured projects from the database
2. Every minute, it checks if any project needs voting
3. When voting time arrives:
   - Launches a headless browser
   - Navigates to the voting page
   - Attempts to click the vote button
   - Handles captchas (requires manual intervention)
   - Updates statistics
   - Schedules next vote (24 hours later by default)
4. The dashboard provides a web interface to manage everything

## Troubleshooting

### Container won't start

Check logs:
```bash
docker-compose logs -f
```

### Voting fails

1. Check the project error message in the dashboard
2. View worker logs: `docker-compose logs worker`
3. Some sites may have captchas that require manual solving
4. Ensure the project ID is correct

### Dashboard not accessible

1. Check if container is running: `docker ps`
2. Check port mapping in docker-compose.yml
3. Try accessing via `http://localhost:8080`

### Reset everything

```bash
docker-compose down
rm -rf data/
docker-compose up -d
```

## Comparison with Browser Extension

| Feature | Browser Extension | Docker Container |
|---------|------------------|------------------|
| Installation | Browser store | Docker |
| Runs when | Browser open | 24/7 |
| Resource usage | Browser memory | Dedicated container |
| Dashboard | Browser popup | Web interface |
| Remote access | No | Yes (with proper networking) |
| Multiple servers | No | Yes |
| Automation | Requires browser open | Fully automated |

## Advanced Usage

### Running Behind a Reverse Proxy

Example Nginx configuration:

```nginx
location /auto-vote/ {
    proxy_pass http://localhost:8080/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### Custom Vote Schedules

Edit a project's `time` field in `data/projects.json` to set custom vote times.

### Backup and Restore

**Backup:**
```bash
tar -czf auto-vote-backup.tar.gz data/
```

**Restore:**
```bash
tar -xzf auto-vote-backup.tar.gz
docker-compose restart
```

## Development

### Building from Source

```bash
docker build -t auto-vote-rating .
```

### Running Locally (without Docker)

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run worker
python worker/main.py &

# Run dashboard
python dashboard/app.py
```

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

Same as the original project.

## Support

- **Discord**: https://discord.com/invite/GyvMtbU
- **GitHub Issues**: https://github.com/cancel-cloud/Auto-Vote-Rating/issues

## Credits

- Original browser extension by [Serega007](https://github.com/Serega007RU)
- Docker version containerization

## Migration from Browser Extension

To migrate from the browser extension:

1. Export your projects from the browser extension (if possible)
2. Start the Docker container
3. Manually add each project via the dashboard
4. The voting schedule will continue automatically

Note: Direct migration of extension data is not currently supported, but projects can be manually re-added through the web interface.
