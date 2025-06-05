from flask import Flask, request, jsonify, send_from_directory, render_template
import os
import base64
import json
from datetime import datetime
import logging
import time
import threading
from PIL import Image, ImageDraw, ImageFont
import io
import asyncio
import json
import uuid
import threading
from flask_socketio import SocketIO, emit
import websockets
import eventlet
eventlet.monkey_patch()

app = Flask(__name__,
    template_folder='./template',  # default: 'templates'
    static_folder='./static'       # default: 'static'
)

socketio = SocketIO(app, async_mode="eventlet", cors_allowed_origins="*")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure photos directory exists
PHOTOS_DIR = "photos"
os.makedirs(PHOTOS_DIR, exist_ok=True)

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

@app.route('/api/save_snapshot', methods=['POST'])
def save_snapshot():
    """Save a snapshot sent from the web interface"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        stream_id = data.get('stream_id')
        image_data = data.get('image_data')  # Base64 encoded image
        camera_name = data.get('camera_name', f'Camera {stream_id}')
        
        if not stream_id or not image_data:
            return jsonify({"error": "Missing stream_id or image_data"}), 400
        
        # Remove data URL prefix if present
        if image_data.startswith('data:image'):
            image_data = image_data.split(',')[1]
        
        # Decode base64 image
        try:
            image_bytes = base64.b64decode(image_data)
        except Exception as e:
            return jsonify({"error": f"Invalid base64 data: {str(e)}"}), 400
        
        # Create directory for this camera
        camera_dir = os.path.join(PHOTOS_DIR, str(stream_id))
        os.makedirs(camera_dir, exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{timestamp}.jpg"
        filepath = os.path.join(camera_dir, filename)
        
        # Save image
        with open(filepath, 'wb') as f:
            f.write(image_bytes)
        
        logger.info(f"Snapshot saved: {filepath} for {camera_name}")
        
        return jsonify({
            "success": True,
            "filename": filename,
            "filepath": filepath,
            "message": f"Snapshot from {camera_name} saved successfully"
        })
        
    except Exception as e:
        logger.error(f"Error saving snapshot: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/api/save_multiple_snapshots', methods=['POST'])
def save_multiple_snapshots():
    """Save multiple snapshots at once"""
    try:
        data = request.get_json()
        
        if not data or 'snapshots' not in data:
            return jsonify({"error": "No snapshots data provided"}), 400
        
        results = []
        errors = []
        
        for snapshot in data['snapshots']:
            try:
                stream_id = snapshot.get('stream_id')
                image_data = snapshot.get('image_data')
                camera_name = snapshot.get('camera_name', f'Camera {stream_id}')
                
                if not stream_id or not image_data:
                    errors.append(f"Missing data for camera {stream_id}")
                    continue
                
                # Remove data URL prefix if present
                if image_data.startswith('data:image'):
                    image_data = image_data.split(',')[1]
                
                # Decode base64 image
                image_bytes = base64.b64decode(image_data)
                
                # Create directory for this camera
                camera_dir = os.path.join(PHOTOS_DIR, str(stream_id))
                os.makedirs(camera_dir, exist_ok=True)
                
                # Generate filename with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"{timestamp}.jpg"
                filepath = os.path.join(camera_dir, filename)
                
                # Save image
                with open(filepath, 'wb') as f:
                    f.write(image_bytes)
                
                results.append({
                    "stream_id": stream_id,
                    "camera_name": camera_name,
                    "filename": filename,
                    "filepath": filepath,
                    "success": True
                })
                
                logger.info(f"Snapshot saved: {filepath} for {camera_name}")
                
            except Exception as e:
                error_msg = f"Error saving snapshot for camera {snapshot.get('stream_id', 'unknown')}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        return jsonify({
            "success": True,
            "results": results,
            "errors": errors,
            "saved_count": len(results),
            "error_count": len(errors)
        })
        
    except Exception as e:
        logger.error(f"Error saving multiple snapshots: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/api/list_snapshots')
def list_snapshots():
    """List all saved snapshots"""
    try:
        snapshots = {}
        
        if os.path.exists(PHOTOS_DIR):
            for camera_dir in os.listdir(PHOTOS_DIR):
                camera_path = os.path.join(PHOTOS_DIR, camera_dir)
                if os.path.isdir(camera_path):
                    camera_files = []
                    for file in os.listdir(camera_path):
                        if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                            file_path = os.path.join(camera_path, file)
                            file_stat = os.stat(file_path)
                            camera_files.append({
                                "filename": file,
                                "size": file_stat.st_size,
                                "created": datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
                                "modified": datetime.fromtimestamp(file_stat.st_mtime).isoformat()
                            })
                    
                    camera_files.sort(key=lambda x: x['created'], reverse=True)
                    snapshots[camera_dir] = camera_files
        
        return jsonify({
            "success": True,
            "snapshots": snapshots,
            "total_cameras": len(snapshots)
        })
        
    except Exception as e:
        logger.error(f"Error listing snapshots: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/photos/<camera_id>/<filename>')
def serve_photo(camera_id, filename):
    """Serve a specific photo"""
    try:
        return send_from_directory(os.path.join(PHOTOS_DIR, camera_id), filename)
    except Exception as e:
        logger.error(f"Error serving photo: {str(e)}")
        return jsonify({"error": "Photo not found"}), 404

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "photos_dir": PHOTOS_DIR,
        "photos_dir_exists": os.path.exists(PHOTOS_DIR),
        "available_cameras": [1, 2, 3, 4, 5],
        "api_endpoints": [
            "/api/test_snapshot",
            "/api/test_multiple_snapshots", 
            "/api/snapshot_all",
            "/api/save_snapshot",
            "/api/save_multiple_snapshots",
            "/api/list_snapshots"
        ]
    })

@app.route('/api/test_snapshot', methods=['POST'])
def test_snapshot():
    """Test endpoint for taking a single snapshot (demo mode)"""
    try:
        data = request.get_json()
        camera_id = data.get('camera_id', 1)
        
        # Generate a test image
        test_image = generate_test_image(camera_id)
        
        # Create directory for this camera
        camera_dir = os.path.join(PHOTOS_DIR, str(camera_id))
        os.makedirs(camera_dir, exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{timestamp}.jpg"
        filepath = os.path.join(camera_dir, filename)
        
        # Save test image
        test_image.save(filepath, 'JPEG', quality=90)
        
        # Convert to base64 for response
        img_buffer = io.BytesIO()
        test_image.save(img_buffer, format='JPEG', quality=90)
        img_buffer.seek(0)
        image_b64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
        
        logger.info(f"Test snapshot saved: {filepath} for Camera {camera_id}")
        
        return jsonify({
            "success": True,
            "camera_id": camera_id,
            "filename": filename,
            "filepath": filepath,
            "image_data": image_b64,
            "timestamp": timestamp,
            "message": f"Test snapshot from Camera {camera_id} captured successfully"
        })
        
    except Exception as e:
        logger.error(f"Error taking test snapshot: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/api/test_multiple_snapshots', methods=['POST'])
def test_multiple_snapshots():
    """Test endpoint for taking synchronized multiple snapshots (demo mode)"""
    try:
        data = request.get_json()
        camera_ids = data.get('camera_ids', [1, 2, 3, 4, 5])
        
        if not isinstance(camera_ids, list):
            return jsonify({"error": "camera_ids must be a list"}), 400
        
        # Ensure synchronized capture by using the same timestamp
        base_timestamp = datetime.now()
        timestamp_str = base_timestamp.strftime("%Y%m%d_%H%M%S_%f")
        
        results = {}
        errors = []
        
        # Generate all images with the same timestamp for synchronization
        for camera_id in camera_ids:
            try:
                # Generate a test image
                test_image = generate_test_image(camera_id, base_timestamp)
                
                # Create directory for this camera
                camera_dir = os.path.join(PHOTOS_DIR, str(camera_id))
                os.makedirs(camera_dir, exist_ok=True)
                
                # Use synchronized timestamp
                filename = f"{timestamp_str}.jpg"
                filepath = os.path.join(camera_dir, filename)
                
                # Save test image
                test_image.save(filepath, 'JPEG', quality=90)
                
                # Convert to base64 for response
                img_buffer = io.BytesIO()
                test_image.save(img_buffer, format='JPEG', quality=90)
                img_buffer.seek(0)
                image_b64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
                
                results[str(camera_id)] = {
                    "success": True,
                    "camera_id": camera_id,
                    "filename": filename,
                    "filepath": filepath,
                    "image_data": image_b64,
                    "timestamp": timestamp_str,
                    "message": f"Test snapshot from Camera {camera_id} captured successfully"
                }
                
                logger.info(f"Synchronized test snapshot saved: {filepath} for Camera {camera_id}")
                
            except Exception as e:
                error_msg = f"Error capturing from camera {camera_id}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        return jsonify({
            "success": True,
            "snapshots": results,
            "timestamp": timestamp_str,
            "captured_count": len(results),
            "error_count": len(errors),
            "errors": errors,
            "message": f"Synchronized snapshots captured from {len(results)} cameras"
        })
        
    except Exception as e:
        logger.error(f"Error taking multiple test snapshots: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/api/snapshot_all', methods=['POST'])
def snapshot_all():
    """Convenience endpoint for taking synchronized snapshots from all cameras"""
    try:
        # Redirect to multiple snapshots with all cameras
        return test_multiple_snapshots_internal([1, 2, 3, 4, 5])
        
    except Exception as e:
        logger.error(f"Error taking all snapshots: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500



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



def run_async(func):
    return asyncio.run(func)



@socketio.on("connect")
def handle_connect():
    print("Client connesso")


if __name__ == '__main__':
    # Production configuration

    print("Web interface: http://127.0.0.1:5001")
    socketio.run(app, 
        host="127.0.0.1",
        debug=True,    
        port=5001
    )
