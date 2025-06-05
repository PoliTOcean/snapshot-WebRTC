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
                self._save_locally(result['image'], camera_id, local_path)
            
            return result
            
        except requests.RequestException as e:
            raise SnapshotError(f"Failed to take snapshot from camera {camera_id}: {e}")

    
    def take_multiple_snapshots(self, camera_ids: List[int], save_locally: bool = False, 
                               local_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Take synchronized snapshots from multiple cameras.
        
        This method ensures all snapshots are taken at the exact same moment.
        
        Args:
            camera_ids: List of camera IDs to capture from
            save_locally: Whether to save images locally
            local_path: Custom local path to save images
            
        Returns:
            Dictionary containing all snapshot results
        """
        try:
            response = self.session.post(
                f"{self.server_url}/api/test_multiple_snapshots",
                json={"camera_ids": camera_ids},
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()
            
            if save_locally and result.get('success'):
                for camera_id in camera_ids:
                    if str(camera_id) in result.get('snapshots', {}):
                        self._save_locally(result['snapshots'][str(camera_id)], camera_id, local_path)
            
            return result
            
        except requests.RequestException as e:
            raise SnapshotError(f"Failed to take multiple snapshots: {e}")
    
    def take_all_snapshots(self, save_locally: bool = False, 
                          local_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Take synchronized snapshots from all available cameras.
        
        Args:
            save_locally: Whether to save images locally
            local_path: Custom local path to save images
            
        Returns:
            Dictionary containing snapshot results from all cameras
        """
        camera_ids = self.get_available_cameras()
        return self.take_multiple_snapshots(camera_ids, save_locally, local_path)
    
    def take_burst_snapshots(self, camera_ids: List[int], count: int = 3, 
                           interval: float = 0.5, save_locally: bool = False,
                           local_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Take a burst of synchronized snapshots over time.
        
        Args:
            camera_ids: List of camera IDs to capture from
            count: Number of snapshots to take
            interval: Time interval between snapshots in seconds
            save_locally: Whether to save images locally
            local_path: Custom local path to save images
            
        Returns:
            List of snapshot results
        """
        results = []
        for i in range(count):
            if i > 0:
                time.sleep(interval)
            result = self.take_multiple_snapshots(camera_ids, save_locally, local_path)
            results.append(result)
        return results
    
    def _save_locally(self, snapshot_data: str, camera_id: int, 
                     local_path: Optional[str] = None):
        """Save snapshot data locally."""
        try:
            if snapshot_data:
                # Decode base64 image data
                image_data = base64.b64decode(snapshot_data)
                
                # Determine save path
                if local_path:
                    save_path = Path(local_path)
                else:
                    save_path = Path.cwd() / "snapshots"
                
                save_path.mkdir(exist_ok=True)
                
                # Generate filename
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"camera_{camera_id}_{timestamp}.jpg"
                file_path = save_path / filename
                
                # Save image
                with open(file_path, 'wb') as f:
                    f.write(image_data)
                
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
        
    except SnapshotError as e:
        print(f"✗ Snapshot client error: {e}")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
