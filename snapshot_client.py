#!/usr/bin/env python3
"""
Snapshot Client Library

A Python library for taking real-time snapshots from ROV camera streams.
Supports single and multi-camera synchronized snapshots.

Usage:
    from snapshot_client import SnapshotClient
    
    # Initialize client
    client = SnapshotClient("http://localhost:5001")
    
    # Take single snapshot
    result = client.take_snapshot(camera_id=1)
    
    # Take synchronized multi-camera snapshots
    result = client.take_multiple_snapshots([1, 2, 3])
"""

import requests
import json
import time
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import base64
from datetime import datetime
import io
from PIL import Image
from datetime import datetime
from pathlib import Path


class SnapshotError(Exception):
    """Custom exception for snapshot operations"""
    pass


class SnapshotClient:
    """
    Client library for ROV camera snapshot system.
    
    Provides easy-to-use methods for taking synchronized snapshots
    from single or multiple cameras.
    """
    
    def __init__(self, server_url: str = "http://localhost:5001", timeout: int = 300):
        """
        Initialize the snapshot client.
        
        Args:
            server_url: URL of the snapshot server (default: http://localhost:5001)
            timeout: Request timeout in seconds (default: 30)
        """
        self.server_url = server_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
        
        # Test connection
        try:
            response = self.session.get(f"{self.server_url}/api/health", timeout=5)
            if response.status_code != 200:
                raise SnapshotError(f"Server not responding correctly: {response.status_code}")
        except requests.RequestException as e:
            raise SnapshotError(f"Cannot connect to snapshot server: {e}")
    
    def get_server_status(self) -> Dict[str, Any]:
        """
        Get server status and configuration.
        
        Returns:
            Dictionary containing server status information
        """
        try:
            response = self.session.get(f"{self.server_url}/api/health", timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise SnapshotError(f"Failed to get server status: {e}")
    
    def take_snapshot(self, camera_id: int, save_locally: bool = True, 
                 local_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Take a snapshot from a single camera.
        
        Args:
            camera_id: ID of the camera (1-5)
            save_locally: Whether to save the image locally
            local_path: Custom local path to save the image
            
        Returns:
            Dictionary containing snapshot result with file paths and metadata
        """
        try:
            response = self.session.get(
                f"{self.server_url}/api/snapshot",
                params={"id": camera_id},  # parametro corretto in query string
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()
            
            if (result):
                self._save_locally(result['image'], camera_id, "single")
            
            return result
            
        except requests.RequestException as e:
            raise SnapshotError(f"Failed to take snapshot from camera {camera_id}: {e}")

    
    def take_all_snapshots(self, save_locally: bool = True, local_path: Optional[str] = None) -> Dict[int, str]:
        """
        Take snapshots from all cameras via /api/snapshot_all.

        Args:
            save_locally: Whether to save images locally
            local_path: Custom local path to save the images

        Returns:
            Dictionary mapping camera_id -> base64 image string
        """
        try:
            response = self.session.get(
                f"{self.server_url}/api/snapshot_all",
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()

            images =  result.get('images', {}).get('data', [])

            snapshots = {}

            for image_info in images:
                camera_id_str = image_info["stream_id"]
                image_data = image_info["image_data"]
                if camera_id_str is None or image_data is None:
                    continue  # skip invalid entries
                try:
                    camera_id = int(camera_id_str)
                    if save_locally:
                        self._save_locally(image_data, camera_id, "all")
                    snapshots[camera_id] = image_data
                except (ValueError, TypeError):
                    continue  # skip malformed IDs

            return snapshots

        except requests.RequestException as e:
            raise SnapshotError(f"Failed to take all snapshots: {e}")

    
    def take_snapshot_stereo(self, save_locally: bool = True, local_path: Optional[str] = None) -> Dict[int, dict]:
        """
        Take a stereo snapshot (camera 1 and 2 simultaneously) via /api/snapshot_stereo.

        Args:
            save_locally: Whether to save the images locally
            local_path: Optional path to save the images

        Returns:
            Dictionary mapping camera ID -> snapshot data
        """
        try:
            response = self.session.get(
                f"{self.server_url}/api/snapshot_stereo",
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()

            images = result.get("images", {}).get("data", {})

            snapshots = {}

            for image_info in images:
                camera_id_str = image_info["stream_id"]
                image_data = image_info["image_data"]
                if camera_id_str is None or image_data is None:
                    continue  # skip invalid entries
                try:
                    camera_id = int(camera_id_str)
                    if save_locally:
                        self._save_locally(image_data, camera_id, "stereo")
                    snapshots[camera_id] = image_data
                except (ValueError, TypeError):
                    continue  # skip malformed IDs

            return snapshots

        except requests.RequestException as e:
            raise SnapshotError(f"Failed to take stereo snapshots: {e}")


    def _save_locally(self, snapshot_data: str, camera_id: int, dirname: Optional[str] = None):
        """Save snapshot data locally inside 'snapshots/dirname' folder (or just 'snapshots' if dirname is None)."""
        try:
            if snapshot_data:
                # Rimuovi prefisso data URL se presente
                if snapshot_data.startswith("data:"):
                    snapshot_data = snapshot_data.split(",", 1)[1]

                # Decodifica base64 con validazione
                image_data = base64.b64decode(snapshot_data, validate=True)

                # Apri immagine con PIL per determinare formato
                image = Image.open(io.BytesIO(image_data))
                image_format = image.format.lower()

                # Base path: current working dir + 'snapshots' + optional dirname
                base_path = Path.cwd() / "snapshots"
                if dirname:
                    base_path = base_path / dirname
                base_path.mkdir(parents=True, exist_ok=True)

                # Crea filename con timestamp e formato corretto
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"camera_{camera_id}_{timestamp}.{image_format}"
                file_path = base_path / filename

                # Salva immagine
                image.save(file_path)

                print(f"Snapshot saved locally: {file_path}")

        except Exception as e:
            print(f"Failed to save snapshot locally: {e}")


    
    def download_snapshot(self, snapshot_path: str, local_path: Optional[str] = None) -> str:
        """
        Download a snapshot from the server.
        
        Args:
            snapshot_path: Server path to the snapshot
            local_path: Local path to save the file
            
        Returns:
            Local path where the file was saved
        """
        try:
            response = self.session.get(
                f"{self.server_url}/photos/{snapshot_path}",
                timeout=self.timeout
            )
            response.raise_for_status()
            
            # Determine save path
            if local_path:
                save_path = Path(local_path)
            else:
                save_path = Path.cwd() / "downloaded_snapshots" / Path(snapshot_path).name
            
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save file
            with open(save_path, 'wb') as f:
                f.write(response.content)
            
            return str(save_path)
            
        except requests.RequestException as e:
            raise SnapshotError(f"Failed to download snapshot: {e}")

if __name__ == "__main__":
    """Demo usage of the snapshot client library."""
    
    print("=== Snapshot Client Library Demo ===")
    
    # Initialize client
    try:
        client = SnapshotClient()
        print("✓ Connected to snapshot server")

        client.take_snapshot(1)
        print("✓ Taken first snapshot")

        client.take_all_snapshots()
        print("✓ Taken all snapshots")

        client.take_snapshot_stereo()
        print("✓ Taken stereo snapshot")
        
    except SnapshotError as e:
        print(f"✗ Snapshot client error: {e}")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
