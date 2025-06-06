import eventlet
eventlet.monkey_patch()
from flask import Flask, request, jsonify, render_template
import os
import json
from datetime import datetime
import logging
import threading
from PIL import Image, ImageDraw, ImageFont
import asyncio
import json
import threading
from flask_socketio import SocketIO, emit
import websockets


app = Flask(__name__,
    template_folder='./template',  # default: 'templates'
    static_folder='./static'       # default: 'static'
)

socketio = SocketIO(app, async_mode="eventlet", 
                    cors_allowed_origins="*", 
                    max_http_buffer_size=100 * 1024 * 1024,
                    )

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.route('/')
def index():
    """Serve the snapshot web viewer"""
    try:
        return render_template("snapshot_web_viewer.html")
    except FileNotFoundError:
        return jsonify({"error": "snapshot_web_viewer.html not found"}), 404

@app.route('/api/config')
def get_config():
    """Get configuration for the web interface"""
    try:
        with open('snapshot_config.json', 'r') as f:
            config = json.load(f)
        return jsonify(config)
    except FileNotFoundError:
        # Return default configuration
        default_config = {
            "janus": {
                "server": "10.0.0.192",
                "port": 8188,
                "use_ssl": False,
                "websocket_path": "/janus"
            },
            "snapshots": {
                "save_to_server": True,
                "save_to_browser": True,
                "image_quality": 0.9,
                "image_format": "jpeg"
            },
            "ui": {
                "auto_connect": True,
                "show_fisheye_correction": True
            }
        }
        return jsonify(default_config)
    except Exception as e:
        logger.error(f"Error loading config: {str(e)}")
        return jsonify({"error": f"Error loading config: {str(e)}"}), 500

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "api_endpoints": [
            "/api/snapshot",
            "/api/snapshots_all", 
            "/api/snapshot_stereo",
        ]
    })


### ! TAKE SNAPSHOT

condition = threading.Condition()
snapshots = {}

@app.route('/api/snapshot')
def snapshot():
    camera_id = request.args.get('id')
    if not camera_id:
        return jsonify({'error': 'Missing id'}), 400

    with condition:
        snapshots.pop(camera_id, None)
        socketio.emit('take_snapshot', {'id': camera_id})

        received = condition.wait(timeout=5)  
        if not received or camera_id not in snapshots:
            return jsonify({'error': 'Timeout or no snapshot received'}), 504

        img_base64 = snapshots.pop(camera_id)
        return jsonify({'image': img_base64}), 200

@socketio.on('snapshot_response')
def handle_snapshot_response(data):
    camera_id = data.get('id')
    img_base64 = data.get('image')

    if camera_id and img_base64:
        with condition:
            snapshots[camera_id] = img_base64
            condition.notify_all()

### ! TAKE ALL SNAPSHOT


condition_all = threading.Condition()
snapshots_all = {} 

@app.route('/api/snapshot_all')
def snapshot_all():
    with condition_all:
        snapshots_all.clear()

        socketio.emit('take_all_snapshot')

        received = condition_all.wait(timeout=8)


        if not received or not snapshots_all:
            return jsonify({'error': 'Timeout or no snapshots received'}), 504

        return jsonify({'images': snapshots_all}), 200

@socketio.on('snapshots_all_response')
def handle_snapshots_all_response(data):
    images = data
    if isinstance(images, dict) and images:
        with condition_all:
            snapshots_all.update(images)
            condition_all.notify_all()

def run_async(func):
    return asyncio.run(func)


### ! TAKE STEREO CAMERA

condition_stereo = threading.Condition()
snapshots_stereo = {} 

@app.route('/api/snapshot_stereo')
def snapshot_stereo():
    with condition_stereo:
        snapshots_stereo.clear()
        # Trigger client-side snapshot for camera 1 and 2
        socketio.emit('take_stereo_snapshot')

        # Wait for both snapshots
        received = condition_stereo.wait(timeout=8)

        if not received:
            return jsonify({'error': 'Timeout or incomplete stereo snapshots'}), 504

        return jsonify({'images': snapshots_stereo}), 200

@socketio.on('snapshots_stereo_response')
def handle_snapshots_stereo_response(data):

    if isinstance(data, dict) and data:
        with condition_stereo:
            print(data)
            snapshots_stereo.update(data)
            condition_stereo.notify_all()


def run_async(func):
    return asyncio.run(func)





@socketio.on("connect")
def handle_connect():
    print("Socket connesso")


if __name__ == '__main__':
    # Production configuration

    print("Web interface: http://127.0.0.1:5001")
    socketio.run(app, 
        host="127.0.0.1",
        debug=True,    
        port=5001,
    )
