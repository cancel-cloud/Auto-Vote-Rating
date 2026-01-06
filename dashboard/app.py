"""
Flask web dashboard for Auto-Vote-Rating.
Provides a web interface similar to the browser extension's options.html.
"""
import os
import sys
import json
import logging
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory

# Add worker directory to path to import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'worker'))

from database import Database
from config import Config
from sites import parse_vote_url, get_supported_sites, build_vote_url

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)

# Initialize config and database
config = Config()
db = Database(config.data_dir)
db.initialize()

DEFAULT_URL_EXAMPLE = "https://minecraft-server.eu/vote/index/208F7/"
def build_devtools_frontend_url(cdp_url: str) -> str:
    """
    Resolve the Chrome DevTools frontend URL for a remote debugging target.
    """
    list_url = urllib.parse.urljoin(cdp_url.rstrip("/") + "/", "json/list")
    with urllib.request.urlopen(list_url, timeout=5) as resp:
        targets = json.load(resp)

    def pick_target():
        for target in targets:
            if target.get("type") != "page":
                continue
            target_url = target.get("url") or ""
            if target_url and target_url != "about:blank":
                return target
        return targets[0] if targets else None

    target = pick_target()
    if not target:
        raise RuntimeError("No page targets available for manual browser")

    frontend_path = target.get("devtoolsFrontendUrl") or target.get("devtoolsFrontendUrlCompat")
    if not frontend_path:
        ws = target.get("webSocketDebuggerUrl")
        if not ws:
            raise RuntimeError("DevTools frontend URL not available for manual browser")
        frontend_path = f"/devtools/inspector.html?ws={ws.replace('ws://', '').replace('wss://', '')}"

    if frontend_path.startswith(("http://", "https://")):
        return frontend_path

    base = cdp_url.rstrip("/")
    return urllib.parse.urljoin(base + "/", frontend_path.lstrip("/"))


def resolve_vote_target(payload: dict) -> tuple[str, str, str]:
    """
    Resolve the canonical vote site, project id and normalized URL
    based on provided voteUrl or manual overrides.
    """
    vote_url = payload.get('voteUrl') or payload.get('voteURL')
    manual_override = payload.get('manualOverride', False)
    rating = payload.get('rating')
    project_id = payload.get('id') or payload.get('projectId')
    normalized_url = None

    if vote_url:
        parsed = parse_vote_url(vote_url)
        if parsed:
            rating = parsed['siteKey']
            project_id = parsed['projectId']
            normalized_url = parsed['normalizedUrl']
        elif not manual_override:
            raise ValueError(f"Unknown or invalid vote URL. Example: {DEFAULT_URL_EXAMPLE}")

    if not rating or not project_id:
        raise ValueError("Vote site and project ID are required")

    if not normalized_url:
        normalized_url = build_vote_url(rating, project_id)

    if not normalized_url:
        raise ValueError(f"Unknown vote site. Example: {DEFAULT_URL_EXAMPLE}")

    return rating, str(project_id).strip(), normalized_url

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')


@app.route('/api/projects', methods=['GET'])
def get_projects():
    """Get all projects"""
    try:
        projects = db.get_all_projects()
        return jsonify({'success': True, 'projects': projects})
    except Exception as e:
        logger.error(f"Error getting projects: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/projects/status', methods=['GET'])
def get_project_status():
    """Return lightweight runtime status for polling."""
    try:
        projects = db.get_all_projects()
        summary = []
        for project in projects:
            summary.append({
                'key': project['key'],
                'rating': project.get('rating'),
                'name': project.get('name'),
                'id': project.get('id'),
                'runtime': project.get('runtime', {}),
                'stats': project.get('stats', {}),
            })
        return jsonify({'success': True, 'projects': summary})
    except Exception as e:
        logger.error(f"Error getting project status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/projects/<key>', methods=['GET'])
def get_project(key):
    """Get a specific project"""
    try:
        project = db.get_project(key)
        if project:
            return jsonify({'success': True, 'project': project})
        else:
            return jsonify({'success': False, 'error': 'Project not found'}), 404
    except Exception as e:
        logger.error(f"Error getting project: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/projects', methods=['POST'])
def add_project():
    """Add a new project"""
    try:
        payload = request.json or {}
        rating, project_id, vote_url = resolve_vote_target(payload)
        project_data = {
            'rating': rating,
            'id': project_id,
            'voteUrl': vote_url,
            'nick': payload.get('nick'),
            'name': payload.get('name'),
            'notes': payload.get('notes'),
        }
        key = db.add_project(project_data)
        project = db.get_project(key)
        return jsonify({'success': True, 'project': project})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        logger.error(f"Error adding project: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/projects/<key>', methods=['PUT'])
def update_project(key):
    """Update a project"""
    try:
        payload = request.json or {}
        project = db.get_project(key)
        if not project:
            return jsonify({'success': False, 'error': 'Project not found'}), 404
        vote_fields = {'voteUrl', 'voteURL', 'rating', 'id', 'projectId', 'manualOverride'}
        if vote_fields.intersection(payload.keys()):
            try:
                rating, project_id, vote_url = resolve_vote_target({**project, **payload})
                project['rating'] = rating
                project['id'] = project_id
                project['voteUrl'] = vote_url
            except ValueError as ve:
                return jsonify({'success': False, 'error': str(ve)}), 400
        for key_name, value in payload.items():
            if key_name in vote_fields:
                continue
            project[key_name] = value
        db.update_project(project)
        return jsonify({'success': True, 'project': project})
    except Exception as e:
        logger.error(f"Error updating project: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/projects/<key>', methods=['DELETE'])
def delete_project(key):
    """Delete a project"""
    try:
        db.delete_project(key)
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting project: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get settings"""
    try:
        settings = db.get_settings()
        return jsonify({'success': True, 'settings': settings})
    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Update settings"""
    try:
        settings_data = request.json
        db.update_settings(settings_data)
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/storage-health', methods=['GET'])
def storage_health():
    """Return current storage details for debug panel."""
    try:
        health = db.get_storage_health()
        health['dashboardDataDir'] = config.data_dir
        return jsonify({'success': True, 'health': health})
    except Exception as e:
        logger.error(f"Error fetching storage health: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get statistics"""
    try:
        stats = db.get_stats()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/parse-vote-url', methods=['POST'])
def api_parse_vote_url():
    """Parse vote URL on demand (used by UI)."""
    try:
        payload = request.json or {}
        url = payload.get('url')
        if not url:
            return jsonify({'success': False, 'error': 'URL is required'}), 400
        parsed = parse_vote_url(url)
        if not parsed:
            return jsonify({'success': False, 'error': f'Unknown vote site. Example: {DEFAULT_URL_EXAMPLE}'}), 400
        return jsonify({'success': True, 'result': parsed})
    except Exception as e:
        logger.error(f"Error parsing vote URL: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for monitoring"""
    try:
        # Check if database is accessible
        db.get_settings()
        return jsonify({
            'status': 'healthy',
            'service': 'auto-vote-rating',
            'timestamp': datetime.now().isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 503


@app.route('/api/sites', methods=['GET'])
def list_supported_sites():
    """List vote sites for UI."""
    try:
        sites = get_supported_sites()
        return jsonify({'success': True, 'sites': sites})
    except Exception as e:
        logger.error(f"Error getting sites: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/projects/<key>/restart', methods=['POST'])
def restart_project(key):
    """Restart voting for a project (vote now)"""
    try:
        project = db.queue_vote_now(key, source='dashboard-legacy')
        if not project:
            return jsonify({'success': False, 'error': 'Project not found'}), 404
        return jsonify({'success': True, 'project': project})
    except Exception as e:
        logger.error(f"Error restarting project: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/projects/<key>/vote-now', methods=['POST'])
def vote_now(key):
    """Queue an immediate vote attempt, returning the updated status."""
    try:
        project = db.queue_vote_now(key, source='dashboard')
        if not project:
            return jsonify({'success': False, 'error': 'Project not found'}), 404
        return jsonify({'success': True, 'project': project})
    except Exception as e:
        logger.error(f"Error queueing vote-now: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/logs/download', methods=['GET'])
def download_logs():
    """Download worker logs"""
    try:
        source = request.args.get('source', 'worker')
        if source == 'debug':
            log_file = os.path.join(config.data_dir, 'debug.log.jsonl')
            download_name = 'debug.log.jsonl'
        else:
            log_file = os.path.join(config.data_dir, 'worker.log')
            download_name = 'worker.log'
        if os.path.exists(log_file):
            from flask import send_file
            return send_file(log_file, as_attachment=True, download_name=download_name)
        else:
            return jsonify({'success': False, 'error': 'Log file not found'}), 404
    except Exception as e:
        logger.error(f"Error downloading logs: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/logs', methods=['GET'])
def list_logs():
    """Return debug logs (newest first)."""
    try:
        limit = int(request.args.get('limit', 200))
        limit = max(1, min(limit, 1000))
        project_key = request.args.get('projectKey')
        logs = db.get_logs(limit=limit, project_key=project_key)
        return jsonify({'success': True, 'logs': logs})
    except Exception as e:
        logger.error(f"Error loading logs: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =================================================================
# Manual Browser Control API (for captcha solving)
# =================================================================

@app.route('/api/projects/<key>/request-manual-browser', methods=['POST'])
def request_manual_browser(key):
    """
    Request worker to launch headful browser with CDP.
    Worker will pick this up on next tick (within 60 seconds).
    """
    try:
        project = db.get_project(key)
        if not project:
            return jsonify({'success': False, 'error': 'Project not found'}), 404

        runtime = project.get('runtime', {})
        if runtime.get('status') != 'NEEDS_USER_ACTION':
            return jsonify({
                'success': False,
                'error': 'Project not in NEEDS_USER_ACTION state'
            }), 400

        # Set flag for worker to pick up
        runtime['manualBrowserRequested'] = True
        db.update_project(project)

        logger.info(f"Manual browser requested for {key}")
        return jsonify({
            'success': True,
            'message': 'Browser launch requested - will start within 60 seconds',
            'project': project
        })
    except Exception as e:
        logger.error(f"Error requesting manual browser: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/projects/<key>/complete-manual-solve', methods=['POST'])
def complete_manual_solve(key):
    """
    Mark captcha as solved and resume automation.
    Closes headful browser and schedules next vote.
    """
    try:
        project = db.get_project(key)
        if not project:
            return jsonify({'success': False, 'error': 'Project not found'}), 404

        runtime = project.get('runtime', {})

        # Set flag for worker to pick up and process
        runtime['manualSolveCompleted'] = True
        db.update_project(project)

        logger.info(f"Manual solve completed for {key}")
        return jsonify({
            'success': True,
            'message': 'Resume requested - worker will process within 60 seconds',
            'project': project
        })

    except Exception as e:
        logger.error(f"Error completing manual solve: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/projects/<key>/cdp-info', methods=['GET'])
def get_cdp_info(key):
    """Get CDP connection info for manual browser."""
    try:
        project = db.get_project(key)
        if not project:
            return jsonify({'success': False, 'error': 'Project not found'}), 404

        runtime = project.get('runtime', {})
        cdp_url = runtime.get('cdpUrl')

        if not cdp_url:
            return jsonify({
                'success': False,
                'error': 'Manual browser not active'
            }), 400

        frontend_url = None
        try:
            frontend_url = build_devtools_frontend_url(cdp_url)
        except Exception as e:
            logger.warning(f"Failed to resolve DevTools frontend URL: {e}")

        payload = {
            'success': True,
            'cdpUrl': cdp_url,
            'authToken': config.cdp_auth_token,
            'instructions': f'Access browser at: {cdp_url}',
        }
        if frontend_url:
            payload['frontendUrl'] = frontend_url

        return jsonify(payload)
    except Exception as e:
        logger.error(f"Error getting CDP info: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =================================================================
# Static file serving
# =================================================================

# Serve static files (CSS, JS, images)
@app.route('/css/<path:filename>')
def serve_css(filename):
    """Serve CSS files"""
    return send_from_directory('../css', filename)


@app.route('/images/<path:filename>')
def serve_images(filename):
    """Serve image files"""
    return send_from_directory('../images', filename)


@app.route('/fonts/<path:filename>')
def serve_fonts(filename):
    """Serve font files"""
    return send_from_directory('../fonts', filename)


def main():
    """Run the dashboard"""
    logger.info(f"Starting dashboard on {config.dashboard_host}:{config.dashboard_port}")
    app.run(
        host=config.dashboard_host,
        port=config.dashboard_port,
        debug=config.debug
    )


if __name__ == '__main__':
    main()
