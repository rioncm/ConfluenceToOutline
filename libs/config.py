"""
Configuration management for the Confluence processing system.

This module provides centralized configuration with validation and type safety.
"""
import os
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from pathlib import Path


@dataclass
class LoggingConfig:
    """Logging configuration."""
    log_level: int = field(default_factory=lambda: getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper(), logging.INFO))
    log_file: Optional[str] = field(default_factory=lambda: os.getenv('LOG_FILE'))
    
    def get_level_name(self) -> str:
        """Get the logging level name."""
        return logging.getLevelName(self.log_level)
    
    @classmethod
    def from_args(cls, args) -> 'LoggingConfig':
        """Create config from command line arguments."""
        return cls()


@dataclass
class ProcessingConfig:
    """Configuration for HTML and content processing."""
    preserve_breadcrumbs: bool = True
    preserve_titles: bool = True
    parallel_workers: int = 4
    
    @classmethod 
    def from_args(cls, args) -> 'ProcessingConfig':
        """Create config from command line arguments."""
        return cls(
            preserve_breadcrumbs=getattr(args, 'preserve_breadcrumbs', True),
            preserve_titles=getattr(args, 'preserve_titles', True)
        )


@dataclass
class SecurityConfig:
    """Security-related configuration for file processing."""
    max_file_size: int = 100 * 1024 * 1024  # 100MB per file
    max_total_size: int = 1024 * 1024 * 1024  # 1GB total extraction
    max_files: int = 10000  # Maximum files per archive
    allowed_extensions: list = field(default_factory=lambda: [
        '.html', '.md', '.txt', '.png', '.jpg', '.jpeg', '.gif', 
        '.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt'
    ])
    
    def __post_init__(self):
        """Apply environment variable overrides for extensions."""
        # Check for OVERRIDE_EXTENSIONS (replaces default list)
        override_extensions = os.getenv('OVERRIDE_EXTENSIONS')
        if override_extensions:
            # Parse comma-separated list and ensure extensions start with dot
            extensions = [ext.strip() for ext in override_extensions.split(',')]
            extensions = [ext if ext.startswith('.') else f'.{ext}' for ext in extensions if ext.strip()]
            if extensions:  # Only override if we got valid extensions
                self.allowed_extensions = extensions
                
        # Check for INCLUDE_EXTENSIONS (adds to existing list)  
        include_extensions = os.getenv('INCLUDE_EXTENSIONS')
        if include_extensions:
            # Parse comma-separated list and ensure extensions start with dot
            extensions = [ext.strip() for ext in include_extensions.split(',')]
            extensions = [ext if ext.startswith('.') else f'.{ext}' for ext in extensions if ext.strip()]
            # Add new extensions that aren't already in the list
            for ext in extensions:
                if ext not in self.allowed_extensions:
                    self.allowed_extensions.append(ext)
    
    def is_allowed_file(self, filename: str) -> bool:
        """Check if file extension is allowed."""
        ext = Path(filename).suffix.lower()
        return ext in self.allowed_extensions


@dataclass
class DirectoryConfig:
    """Directory paths configuration."""
    zips_dir: str = 'zips'
    input_dir: str = 'input' 
    output_dir: str = 'output'
    
    def __post_init__(self):
        """Ensure directories exist."""
        for dir_name in [self.zips_dir, self.input_dir, self.output_dir]:
            Path(dir_name).mkdir(exist_ok=True)
    
    @classmethod
    def from_args(cls, args) -> 'DirectoryConfig':
        """Create config from command line arguments."""
        return cls(
            zips_dir=getattr(args, 'zips_dir', 'zips'),
            input_dir=getattr(args, 'input_dir', 'input'),
            output_dir=getattr(args, 'output_dir', 'output')
        )


@dataclass
class APIConfig:
    """API connection configuration."""
    api_key: Optional[str] = field(default_factory=lambda: os.getenv('OUTLINE_API_TOKEN') or os.getenv('OUTLINE_API_KEY'))
    api_url: Optional[str] = field(default_factory=lambda: os.getenv('OUTLINE_API_URL'))
    info_sys_id: str = "75d73899-f8cd-4a95-b537-d44a87e007a8"
    timeout: int = 30
    max_retries: int = 3
    
    def __post_init__(self):
        """Validate API configuration."""
        if not self.api_key or not self.api_url:
            # Don't raise error here, let commands that need API handle it
            pass
    
    def validate(self):
        """Validate API configuration is complete."""
        if not self.api_key or not self.api_url:
            raise ValueError(
                "Missing required environment variables: OUTLINE_API_TOKEN (or OUTLINE_API_KEY) and OUTLINE_API_URL"
            )
    
    @property
    def headers(self) -> Dict[str, str]:
        """Get HTTP headers for API requests."""
        if not self.api_key:
            raise ValueError("API key not configured")
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }


@dataclass
class AppConfig:
    """Main application configuration combining all sub-configs."""
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    directories: DirectoryConfig = field(default_factory=DirectoryConfig) 
    api: APIConfig = field(default_factory=APIConfig)
    
    @classmethod
    def from_args(cls, args) -> 'AppConfig':
        """Create complete config from command line arguments."""
        return cls(
            logging=LoggingConfig.from_args(args),
            processing=ProcessingConfig.from_args(args),
            directories=DirectoryConfig.from_args(args),
            api=APIConfig()
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary for logging/debugging."""
        return {
            'logging': {
                'log_level': self.logging.get_level_name(),
                'log_file': self.logging.log_file
            },
            'processing': {
                'preserve_breadcrumbs': self.processing.preserve_breadcrumbs,
                'preserve_titles': self.processing.preserve_titles,
                'parallel_workers': self.processing.parallel_workers
            },
            'security': {
                'max_file_size': self.security.max_file_size,
                'max_total_size': self.security.max_total_size,
                'max_files': self.security.max_files,
                'allowed_extensions_count': len(self.security.allowed_extensions)
            },
            'directories': {
                'zips_dir': self.directories.zips_dir,
                'input_dir': self.directories.input_dir,
                'output_dir': self.directories.output_dir
            },
            'api': {
                'api_configured': bool(self.api.api_key and self.api.api_url),
                'timeout': self.api.timeout,
                'max_retries': self.api.max_retries
            }
        }


def load_config_from_args(args) -> AppConfig:
    """
    Convenience function to load complete configuration from command line arguments.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        Complete application configuration
    """
    return AppConfig.from_args(args)