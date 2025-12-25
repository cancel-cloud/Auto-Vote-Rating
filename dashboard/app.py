"""
Flask web dashboard for Auto-Vote-Rating.
Provides a web interface similar to the browser extension's options.html.
"""
import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory

# Add worker directory to path to import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'worker'))

from database import Database
from config import Config

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
        project_data = request.json
        
        # Validate required fields
        if 'rating' not in project_data:
            return jsonify({'success': False, 'error': 'Rating is required'}), 400
        
        key = db.add_project(project_data)
        return jsonify({'success': True, 'key': key})
    except Exception as e:
        logger.error(f"Error adding project: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/projects/<key>', methods=['PUT'])
def update_project(key):
    """Update a project"""
    try:
        project_data = request.json
        project_data['key'] = key
        
        db.update_project(project_data)
        return jsonify({'success': True})
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


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get statistics"""
    try:
        stats = db.get_stats()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
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


@app.route('/api/projects/<key>/restart', methods=['POST'])
def restart_project(key):
    """Restart voting for a project (vote now)"""
    try:
        project = db.get_project(key)
        if not project:
            return jsonify({'success': False, 'error': 'Project not found'}), 404
        
        # Clear the next vote time to trigger immediate voting
        project['time'] = None
        db.update_project(project)
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error restarting project: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


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
