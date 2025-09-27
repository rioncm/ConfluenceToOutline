"""
API integration package for the Information Systems Documentation Processor.

This package provides API clients for uploading processed documentation 
to various target systems (Outline, Notion, etc.).
"""

from .base import BaseAPIClient, APIResponse
from .outline import OutlineAPIClient

__all__ = ['BaseAPIClient', 'APIResponse', 'OutlineAPIClient']