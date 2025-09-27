# Development Guide - Phase 3 API Integration

This guide provides detailed instructions for implementing Phase 3 API integration features.

## 🎯 Development Objectives

1. **Reliable API Integration** - Robust upload system with error recovery
2. **Multiple Provider Support** - Extensible architecture for various APIs
3. **Performance Optimization** - Efficient batch processing and uploads
4. **User Experience** - Clear progress and error reporting

## 🏗 Architecture Design

### API Client Architecture
```python
# libs/api/base.py - Abstract base class
class BaseAPIClient(ABC):
    @abstractmethod
    def create_collection(self, name: str) -> APIResponse: pass
    
    @abstractmethod  
    def create_document(self, collection_id: str, title: str, 
                       content: str, parent_id: str = None) -> APIResponse: pass
    
    @abstractmethod
    def upload_attachment(self, file_path: str, document_id: str) -> APIResponse: pass

# libs/api/outline.py - Outline-specific implementation
class OutlineAPIClient(BaseAPIClient):
    def __init__(self, config: APIConfig):
        self.config = config
        self.session = self._create_session()
        
# libs/api/notion.py - Future Notion implementation  
class NotionAPIClient(BaseAPIClient): pass
```

### Upload Orchestrator
```python
# libs/api/uploader.py
class APIUploader:
    def __init__(self, client: BaseAPIClient, config: UploadConfig):
        self.client = client
        self.config = config
        self.progress = UploadProgress()
        self.logger = get_logger('api_uploader')
    
    def upload_structure(self, structure_file: str) -> UploadResult:
        """Main upload orchestration method"""
        
    def _create_navigation_hierarchy(self, navigation: List[Dict]) -> Dict[str, str]:
        """Create collections/folders first"""
        
    def _upload_documents_batch(self, documents: List[Dict]) -> List[UploadResult]:
        """Upload documents in configurable batches"""
        
    def _upload_attachments_batch(self, attachments: List[Dict]) -> List[UploadResult]:
        """Upload attachments separately for efficiency"""
```

### Error Recovery System
```python
# libs/api/recovery.py
class UploadRecovery:
    def __init__(self, checkpoint_file: str):
        self.checkpoint_file = checkpoint_file
        self.state = self._load_checkpoint()
    
    def save_checkpoint(self, progress: UploadProgress): pass
    def can_resume(self) -> bool: pass
    def get_resume_point(self) -> ResumePoint: pass
    
class RetryManager:
    def __init__(self, max_retries: int = 3, backoff_factor: float = 2.0):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
    
    def execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with exponential backoff retry"""
```

## 📋 Implementation Tasks

### Task 1: Base API Infrastructure
**File**: `libs/api/__init__.py`, `libs/api/base.py`

```python
# Define base classes and common interfaces
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

@dataclass
class APIResponse:
    success: bool
    data: Dict[str, Any]
    error: Optional[str] = None
    status_code: Optional[int] = None

class BaseAPIClient(ABC):
    """Abstract base class for all API clients"""
    
    def __init__(self, config: APIConfig):
        self.config = config
        self.logger = get_logger(f'api.{self.__class__.__name__.lower()}')
    
    @abstractmethod
    def test_connection(self) -> APIResponse: 
        """Test API connectivity and authentication"""
        
    @abstractmethod
    def create_collection(self, name: str, description: str = "") -> APIResponse:
        """Create a new collection/workspace"""
        
    @abstractmethod
    def create_document(self, collection_id: str, title: str, 
                       content: str, parent_id: Optional[str] = None) -> APIResponse:
        """Create a document with optional parent relationship"""
        
    @abstractmethod
    def upload_attachment(self, file_path: str, document_id: str, 
                         filename: Optional[str] = None) -> APIResponse:
        """Upload file attachment to document"""
        
    @abstractmethod
    def update_document(self, document_id: str, title: str = None, 
                       content: str = None) -> APIResponse:
        """Update existing document"""
```

### Task 2: Outline API Client
**File**: `libs/api/outline.py`

```python
import requests
from urllib.parse import urljoin
from .base import BaseAPIClient, APIResponse

class OutlineAPIClient(BaseAPIClient):
    """Outline API client implementation"""
    
    def __init__(self, config: APIConfig):
        super().__init__(config)
        self.base_url = config.api_url.rstrip('/')
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({
            'Authorization': f'Bearer {self.config.api_key}',
            'Content-Type': 'application/json'
        })
        session.timeout = self.config.timeout
        return session
    
    def test_connection(self) -> APIResponse:
        try:
            response = self.session.post(
                urljoin(self.base_url, '/api/auth.info')
            )
            return APIResponse(
                success=response.ok,
                data=response.json(),
                status_code=response.status_code
            )
        except Exception as e:
            return APIResponse(success=False, error=str(e))
    
    def create_collection(self, name: str, description: str = "") -> APIResponse:
        try:
            data = {
                'name': name,
                'description': description,
                'color': '#4E5C6E',  # Default color
                'private': False
            }
            response = self.session.post(
                urljoin(self.base_url, '/api/collections.create'),
                json=data
            )
            return APIResponse(
                success=response.ok,
                data=response.json(),
                status_code=response.status_code
            )
        except Exception as e:
            return APIResponse(success=False, error=str(e))
    
    # Implement other abstract methods...
```

### Task 3: Upload Orchestrator
**File**: `libs/api/uploader.py`

```python
from typing import Dict, List, Any, Optional
from pathlib import Path
import json
from tqdm import tqdm
from .base import BaseAPIClient, APIResponse
from ..logger import get_logger

class APIUploader:
    """Orchestrates the complete upload process"""
    
    def __init__(self, client: BaseAPIClient, config: UploadConfig):
        self.client = client
        self.config = config
        self.logger = get_logger('api_uploader')
        self.progress = UploadProgress()
        self.id_mapping = {}  # Maps local IDs to API IDs
    
    def upload_structure_file(self, structure_file: str) -> UploadResult:
        """Upload complete structure from structure.json"""
        self.logger.info(f"Starting upload from {structure_file}")
        
        # Load and validate structure
        structure = self._load_structure(structure_file)
        if not structure:
            return UploadResult(success=False, error="Failed to load structure")
        
        # Test API connection
        if not self._test_connection():
            return UploadResult(success=False, error="API connection failed")
        
        try:
            # Step 1: Create navigation hierarchy
            self._create_navigation_hierarchy(structure['navigation'])
            
            # Step 2: Upload documents in batches
            self._upload_all_documents(structure)
            
            # Step 3: Upload attachments
            self._upload_all_attachments(structure)
            
            # Step 4: Update cross-references
            self._update_cross_references(structure)
            
            # Step 5: Verification
            self._verify_upload(structure)
            
            return UploadResult(success=True, progress=self.progress)
            
        except Exception as e:
            self.logger.error(f"Upload failed: {e}")
            if self.config.rollback_on_failure:
                self._rollback_upload()
            return UploadResult(success=False, error=str(e))
    
    def _create_navigation_hierarchy(self, navigation: List[Dict]) -> None:
        """Create collections and folder structure"""
        for nav_item in tqdm(navigation, desc="Creating navigation structure"):
            if nav_item['type'] == 'navigation':
                collection_response = self.client.create_collection(
                    name=nav_item['title'],
                    description=f"Imported from Confluence - {nav_item['title']}"
                )
                
                if collection_response.success:
                    collection_id = collection_response.data['data']['id']
                    self.id_mapping[tuple(nav_item['path'])] = collection_id
                    self.logger.info(f"Created collection: {nav_item['title']}")
                else:
                    raise Exception(f"Failed to create collection: {collection_response.error}")
```

### Task 4: Error Recovery & Resume
**File**: `libs/api/recovery.py`

```python
import json
import os
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from ..logger import get_logger

@dataclass
class UploadCheckpoint:
    """Represents upload progress state"""
    collections_created: List[str]
    documents_created: Dict[str, str]  # path -> document_id
    attachments_uploaded: Dict[str, str]  # file_path -> attachment_id
    failed_items: List[Dict[str, Any]]
    current_phase: str
    timestamp: str

class UploadRecovery:
    """Handles upload progress tracking and resume capability"""
    
    def __init__(self, checkpoint_file: str = ".upload_checkpoint.json"):
        self.checkpoint_file = checkpoint_file
        self.logger = get_logger('upload_recovery')
        self.checkpoint = self._load_checkpoint()
    
    def save_checkpoint(self, checkpoint: UploadCheckpoint) -> None:
        """Save current progress to checkpoint file"""
        try:
            with open(self.checkpoint_file, 'w') as f:
                json.dump(asdict(checkpoint), f, indent=2)
            self.logger.debug(f"Checkpoint saved: {checkpoint.current_phase}")
        except Exception as e:
            self.logger.error(f"Failed to save checkpoint: {e}")
    
    def load_checkpoint(self) -> Optional[UploadCheckpoint]:
        """Load previous checkpoint if available"""
        return self._load_checkpoint()
    
    def can_resume(self) -> bool:
        """Check if resume is possible"""
        return self.checkpoint is not None
    
    def clear_checkpoint(self) -> None:
        """Remove checkpoint file after successful completion"""
        if os.path.exists(self.checkpoint_file):
            os.remove(self.checkpoint_file)
            self.logger.info("Upload checkpoint cleared")
```

### Task 5: Progress Tracking & UI
**File**: `libs/api/progress.py`

```python
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from tqdm import tqdm
from ..logger import get_logger, ProgressLogger

@dataclass
class UploadStats:
    """Upload statistics and metrics"""
    total_collections: int = 0
    total_documents: int = 0 
    total_attachments: int = 0
    collections_created: int = 0
    documents_uploaded: int = 0
    attachments_uploaded: int = 0
    failed_collections: int = 0
    failed_documents: int = 0
    failed_attachments: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None

class UploadProgress:
    """Manages upload progress display and logging"""
    
    def __init__(self):
        self.stats = UploadStats()
        self.logger = get_logger('upload_progress')
        self.current_phase = "Initializing"
        self.progress_bars = {}
    
    def initialize(self, total_collections: int, total_documents: int, 
                  total_attachments: int) -> None:
        """Initialize progress tracking with totals"""
        self.stats.total_collections = total_collections
        self.stats.total_documents = total_documents
        self.stats.total_attachments = total_attachments
        
        self.logger.info(f"Upload initialized: {total_collections} collections, "
                        f"{total_documents} documents, {total_attachments} attachments")
    
    def start_phase(self, phase_name: str, total_items: int) -> tqdm:
        """Start a new progress phase with tqdm bar"""
        self.current_phase = phase_name
        progress_bar = tqdm(
            total=total_items,
            desc=phase_name,
            unit="items",
            leave=True
        )
        self.progress_bars[phase_name] = progress_bar
        return progress_bar
    
    def update_phase(self, phase_name: str, increment: int = 1, 
                    description: str = None) -> None:
        """Update progress for current phase"""
        if phase_name in self.progress_bars:
            self.progress_bars[phase_name].update(increment)
            if description:
                self.progress_bars[phase_name].set_postfix_str(description)
    
    def complete_phase(self, phase_name: str) -> None:
        """Mark phase as complete"""
        if phase_name in self.progress_bars:
            self.progress_bars[phase_name].close()
            del self.progress_bars[phase_name]
```

## 🧪 Testing Strategy

### Unit Tests
```python
# tests/test_api_client.py
import pytest
from unittest.mock import Mock, patch
from libs.api.outline import OutlineAPIClient
from libs.config import APIConfig

class TestOutlineAPIClient:
    def setup_method(self):
        self.config = APIConfig(
            api_key="test_key",
            api_url="https://test.outline.com"
        )
        self.client = OutlineAPIClient(self.config)
    
    @patch('requests.Session.post')
    def test_create_collection_success(self, mock_post):
        # Mock successful API response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            'data': {'id': 'collection-123', 'name': 'Test Collection'}
        }
        mock_post.return_value = mock_response
        
        result = self.client.create_collection("Test Collection")
        
        assert result.success == True
        assert result.data['data']['id'] == 'collection-123'
        mock_post.assert_called_once()
```

### Integration Tests
```python
# tests/test_api_integration.py
import pytest
import os
from libs.api.uploader import APIUploader
from libs.api.outline import OutlineAPIClient

@pytest.mark.integration
@pytest.mark.skipif(not os.getenv('OUTLINE_API_KEY'), reason="No API key provided")
class TestAPIIntegration:
    def setup_method(self):
        config = APIConfig(
            api_key=os.getenv('OUTLINE_API_KEY'),
            api_url=os.getenv('OUTLINE_API_URL')
        )
        self.client = OutlineAPIClient(config)
        self.uploader = APIUploader(self.client, UploadConfig())
    
    def test_full_upload_workflow(self):
        # Test with minimal structure
        test_structure = {
            'navigation': [
                {
                    'title': 'Test Collection',
                    'type': 'navigation',
                    'path': ['Test Collection'],
                    'pages': [
                        {
                            'title': 'Test Document',
                            'type': 'page',
                            'page_data': {
                                'content': '# Test Document\n\nThis is a test.',
                                'attachments': []
                            }
                        }
                    ]
                }
            ]
        }
        
        result = self.uploader.upload_structure(test_structure)
        assert result.success == True
```

## 📋 Development Milestones

### Milestone 1: Basic API Infrastructure (Week 1)
- [ ] Implement `BaseAPIClient` abstract class
- [ ] Create `OutlineAPIClient` with basic operations
- [ ] Add configuration integration
- [ ] Write unit tests for API client
- [ ] Test basic connectivity

### Milestone 2: Upload Orchestration (Week 2)  
- [ ] Implement `APIUploader` class
- [ ] Add batch processing logic
- [ ] Create progress tracking system
- [ ] Implement error handling
- [ ] Add integration tests

### Milestone 3: Error Recovery (Week 3)
- [ ] Implement checkpoint/resume system
- [ ] Add retry logic with exponential backoff
- [ ] Create rollback capability
- [ ] Test recovery scenarios
- [ ] Add comprehensive error reporting

### Milestone 4: Polish & Documentation (Week 4)
- [ ] Add CLI commands for Phase 3
- [ ] Comprehensive testing
- [ ] Performance optimization
- [ ] User documentation
- [ ] Deployment guide

## 🔧 Development Environment Setup

### Prerequisites
```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Set up pre-commit hooks
pre-commit install

# Create test environment variables
cp .env.example .env.test
# Edit .env.test with test API credentials
```

### Running Tests
```bash
# Unit tests only
pytest tests/ -m "not integration"

# Integration tests (requires API credentials)
pytest tests/ -m integration --env-file .env.test

# All tests with coverage
pytest tests/ --cov=libs --cov-report=html
```

### Code Quality
```bash
# Run linting
flake8 libs/ tests/

# Type checking
mypy libs/

# Format code
black libs/ tests/

# Security scanning
bandit -r libs/
```

This development guide provides the foundation for implementing a robust, scalable API integration system that maintains the high quality and security standards established in Phases 1 and 2.