#!/usr/bin/env python3
"""
API Upload Manager for SpaceProcessor
Handles uploading space content to Outline API using the clean JSON structure
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import requests
from datetime import datetime


class ApiUploadManager:
    """
    Upload space content to Outline API using the clean JSON structure
    
    Features:
    - Creates collections and pages with proper parent-child relationships
    - Tracks UUIDs for created items
    - Updates JSON file with creation status
    - Handles attachments (future feature)
    """
    
    def __init__(self, base_path: Path, api_base_url: str, api_token: str):
        self.base_path = Path(base_path)
        self.output_dir = self.base_path / "output"
        self.api_base_url = api_base_url.rstrip('/')
        self.api_token = api_token
        
        # Set up API session
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        
        # Set up logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
    def upload_space(self, space_key: str) -> bool:
        """
        Upload a complete space to the API
        
        Args:
            space_key: Space key (e.g., 'is')
            
        Returns:
            True if successful, False otherwise
        """
        space_file = self.output_dir / f"{space_key}.json"
        if not space_file.exists():
            self.logger.error(f"Space file not found: {space_file}")
            return False
            
        # Load the space JSON
        with open(space_file, 'r', encoding='utf-8') as f:
            space_data = json.load(f)
            
        # Start upload process
        self.logger.info(f"Starting upload for space: {space_data['space_name']} ({space_key})")
        
        try:
            # Upload all content items
            success = self._upload_content_recursive(
                space_data["space_content"], 
                None  # No parent for root items
            )
            
            if success:
                # Update processing stats
                space_data["processing_stats"]["uploaded_at"] = datetime.now().isoformat()
                space_data["processing_stats"]["upload_successful"] = True
                
                # Save updated JSON
                with open(space_file, 'w', encoding='utf-8') as f:
                    json.dump(space_data, f, indent=2, ensure_ascii=False)
                    
                self.logger.info(f"Successfully uploaded space: {space_key}")
                return True
            else:
                self.logger.error(f"Failed to upload space: {space_key}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error uploading space {space_key}: {e}")
            return False
            
    def _upload_content_recursive(
        self, 
        content_items: List[Dict[str, Any]], 
        parent_uuid: Optional[str]
    ) -> bool:
        """
        Recursively upload content items and their children
        
        Args:
            content_items: List of content items to upload
            parent_uuid: UUID of parent item (None for root items)
            
        Returns:
            True if all items uploaded successfully, False otherwise
        """
        for item in content_items:
            # Skip if already created
            if item.get("created", False):
                self.logger.info(f"Skipping already created item: {item['title']}")
                continue
                
            # Create this item
            success, item_uuid = self._create_item(item, parent_uuid)
            if not success:
                self.logger.error(f"Failed to create item: {item['title']}")
                return False
                
            # Update item with UUID and status
            item["page_uuid"] = item_uuid
            item["parent_uuid"] = parent_uuid
            item["created"] = True
            
            self.logger.info(f"Created {item['type']}: {item['title']} (UUID: {item_uuid})")
            
            # Process children with this item as parent
            if item.get("children"):
                success = self._upload_content_recursive(item["children"], item_uuid)
                if not success:
                    return False
                    
            # Small delay to avoid rate limiting
            time.sleep(0.1)
            
        return True
        
    def _create_item(
        self, 
        item: Dict[str, Any], 
        parent_uuid: Optional[str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Create a single item (collection or page) via API
        
        Args:
            item: Item data from JSON
            parent_uuid: UUID of parent item
            
        Returns:
            Tuple of (success, uuid)
        """
        try:
            if item["type"] == "collection":
                return self._create_collection(item, parent_uuid)
            else:
                return self._create_page(item, parent_uuid)
                
        except Exception as e:
            self.logger.error(f"Error creating item {item['title']}: {e}")
            return False, None
            
    def _create_collection(
        self, 
        item: Dict[str, Any], 
        parent_uuid: Optional[str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Create a collection via API
        
        Args:
            item: Collection item data
            parent_uuid: UUID of parent collection
            
        Returns:
            Tuple of (success, collection_uuid)
        """
        url = f"{self.api_base_url}/collections.create"
        
        # Prepare payload
        payload = {
            "name": item["title"],
            "description": f"Collection imported from Confluence\n\n{item.get('md_content', '')[:500]}...",
            "color": "#4E5C6E",  # Default color
            "icon": "collection"  # Default icon
        }
        
        # Set parent if specified
        if parent_uuid:
            payload["parentDocumentId"] = parent_uuid
            
        response = self.session.post(url, json=payload)
        
        if response.status_code == 200:
            data = response.json()
            collection_uuid = data.get("data", {}).get("id")
            return True, collection_uuid
        else:
            self.logger.error(f"Failed to create collection {item['title']}: {response.status_code} {response.text}")
            return False, None
            
    def _create_page(
        self, 
        item: Dict[str, Any], 
        parent_uuid: Optional[str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Create a page via API
        
        Args:
            item: Page item data  
            parent_uuid: UUID of parent collection/page
            
        Returns:
            Tuple of (success, page_uuid)
        """
        url = f"{self.api_base_url}/documents.create"
        
        # Prepare payload
        payload = {
            "title": item["title"],
            "text": item.get("md_content", f"# {item['title']}\n\nContent not available."),
            "publish": True
        }
        
        # Set parent if specified
        if parent_uuid:
            payload["parentDocumentId"] = parent_uuid
            
        response = self.session.post(url, json=payload)
        
        if response.status_code == 200:
            data = response.json()
            page_uuid = data.get("data", {}).get("id")
            return True, page_uuid
        else:
            self.logger.error(f"Failed to create page {item['title']}: {response.status_code} {response.text}")
            return False, None
            
    def get_upload_status(self, space_key: str) -> Optional[Dict[str, Any]]:
        """
        Get upload status for a space
        
        Args:
            space_key: Space key to check
            
        Returns:
            Status information or None if not found
        """
        space_file = self.output_dir / f"{space_key}.json"
        if not space_file.exists():
            return None
            
        with open(space_file, 'r', encoding='utf-8') as f:
            space_data = json.load(f)
            
        def count_status(items, created_count=0, total_count=0):
            for item in items:
                total_count += 1
                if item.get("created", False):
                    created_count += 1
                    
                if item.get("children"):
                    created_count, total_count = count_status(item["children"], created_count, total_count)
                    
            return created_count, total_count
            
        created_count, total_count = count_status(space_data["space_content"])
        
        return {
            "space_name": space_data["space_name"],
            "space_key": space_data["space_key"],
            "created_items": created_count,
            "total_items": total_count,
            "completion_percentage": (created_count / total_count * 100) if total_count > 0 else 0,
            "upload_started": space_data.get("processing_stats", {}).get("uploaded_at"),
            "upload_successful": space_data.get("processing_stats", {}).get("upload_successful", False)
        }
        
    def reset_upload_status(self, space_key: str) -> bool:
        """
        Reset upload status for a space (mark all items as not created)
        
        Args:
            space_key: Space key to reset
            
        Returns:
            True if successful, False otherwise
        """
        space_file = self.output_dir / f"{space_key}.json"
        if not space_file.exists():
            self.logger.error(f"Space file not found: {space_file}")
            return False
            
        with open(space_file, 'r', encoding='utf-8') as f:
            space_data = json.load(f)
            
        def reset_items(items):
            for item in items:
                item["created"] = False
                item["page_uuid"] = None
                item["parent_uuid"] = None
                
                if item.get("children"):
                    reset_items(item["children"])
                    
        reset_items(space_data["space_content"])
        
        # Remove upload stats
        if "uploaded_at" in space_data.get("processing_stats", {}):
            del space_data["processing_stats"]["uploaded_at"]
        if "upload_successful" in space_data.get("processing_stats", {}):
            del space_data["processing_stats"]["upload_successful"]
            
        # Save updated JSON
        with open(space_file, 'w', encoding='utf-8') as f:
            json.dump(space_data, f, indent=2, ensure_ascii=False)
            
        self.logger.info(f"Reset upload status for space: {space_key}")
        return True


def main():
    """Test the API upload manager"""
    
    # This would normally come from environment variables or config
    API_BASE_URL = "https://your-outline-instance.com/api"
    API_TOKEN = "your-api-token"
    
    base_path = Path("/Users/rion/VSCode/IS")
    manager = ApiUploadManager(base_path, API_BASE_URL, API_TOKEN)
    
    print("=== API UPLOAD MANAGER READY ===")
    print("Available methods:")
    print("- upload_space(space_key)")
    print("- get_upload_status(space_key)")
    print("- reset_upload_status(space_key)")
    
    # List available spaces
    output_dir = Path("/Users/rion/VSCode/IS/output")
    if output_dir.exists():
        space_files = list(output_dir.glob("*.json"))
        available_spaces = [f.stem for f in space_files]
        
        print(f"\n=== AVAILABLE SPACES ===")
        for space_key in available_spaces:
            status = manager.get_upload_status(space_key)
            if status:
                print(f"{space_key}: {status['space_name']} - {status['created_items']}/{status['total_items']} items ({status['completion_percentage']:.1f}%) uploaded")


if __name__ == "__main__":
    main()