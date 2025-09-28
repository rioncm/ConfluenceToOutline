#!/usr/bin/env python3
"""
SpaceProcessor - Clean architecture for processing Confluence exports
Replaces the existing Pages class with a streamlined approach focused on API upload
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString
import html2text
import logging

# Import our existing DOM hierarchy parser
from .dom_hierarchy_parser import DomHierarchyParser


class SpaceProcessor:
    """
    Process Confluence space exports with clean architecture
    
    Workflow:
    1. process_input_directories() -> creates space_key.json files in output/
    2. extract_markdown_content() -> populates md_content fields
    3. api_upload() -> creates pages via API and tracks UUIDs
    """
    
    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        self.output_dir = self.base_path / "output"
        self.input_dir = self.base_path / "input"
        
        # Ensure output directory exists
        self.output_dir.mkdir(exist_ok=True)
        
        # Configure html2text for clean markdown conversion
        self.html2text_converter = html2text.HTML2Text()
        self.html2text_converter.ignore_links = False
        self.html2text_converter.ignore_images = False
        self.html2text_converter.body_width = 0  # No line wrapping
        self.html2text_converter.unicode_snob = True
        
        # Set up logging
        self.logger = logging.getLogger(__name__)
        # Don't set up logging configuration here - it should be done by the calling application
        
    def process_input_directories(self) -> List[str]:
        """
        Process all input directories and create space_key.json files
        
        Returns:
            List of space keys that were processed
        """
        processed_spaces = []
        
        # Find all export directories
        export_dirs = [d for d in self.input_dir.iterdir() if d.is_dir() and d.name.startswith('Export-')]
        
        for export_dir in export_dirs:
            self.logger.info(f"Processing export directory: {export_dir.name}")
            
            # Find space directories within the export
            space_dirs = [d for d in export_dir.iterdir() if d.is_dir()]
            
            for space_dir in space_dirs:
                try:
                    space_key = self.process_space_directory(space_dir, export_dir.name)
                    if space_key:
                        processed_spaces.append(space_key)
                        self.logger.info(f"Successfully processed space: {space_key}")
                        
                except Exception as e:
                    self.logger.error(f"Error processing space {space_dir.name}: {e}")
                    continue
        
        return processed_spaces
    
    def process_space_directory(self, space_dir: Path, export_name: str) -> Optional[str]:
        """
        Process a single space directory and create its JSON file
        
        Args:
            space_dir: Path to the space directory (e.g., input/Export-135853/IS)
            export_name: Name of the export (e.g., Export-135853)
            
        Returns:
            Space key if successful, None otherwise
        """
        # Look for index.html file
        index_file = space_dir / "index.html"
        if not index_file.exists():
            self.logger.warning(f"No index.html found in {space_dir}")
            return None
        
        # Use our DOM hierarchy parser to extract structure
        parser = DomHierarchyParser(space_dir.parent)
        structure = parser.parse_index_html(index_file)
        
        # Extract metadata
        metadata = structure["space_metadata"]
        space_key = metadata.get("space_key", space_dir.name).lower()
        space_name = metadata.get("space_name", space_dir.name)
        description = metadata.get("description", "")
        
        # Build the space content structure
        space_content = self.convert_navigation_to_space_content(
            structure["navigation"], 
            space_dir
        )
        
        # Create the final structure
        space_json = {
            "space_name": space_name,
            "space_key": space_key,
            "description": description,
            "local_folder": f"input/{export_name}/{space_dir.name}",
            "processing_stats": {
                "total_pages": structure["stats"]["total_pages"],
                "total_navigation_nodes": structure["stats"]["total_navigation_nodes"],
                "max_depth": structure["stats"]["max_depth"],
                "processed_at": self.get_current_timestamp()
            },
            "space_content": space_content
        }
        
        # Save to output directory
        output_file = self.output_dir / f"{space_key}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(space_json, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Created {output_file} with {len(space_content)} root items")
        return space_key
    
    def convert_navigation_to_space_content(
        self, 
        navigation: List[Dict[str, Any]], 
        space_dir: Path
    ) -> List[Dict[str, Any]]:
        """
        Convert navigation structure to space_content format
        
        Args:
            navigation: Navigation structure from DOM parser
            space_dir: Path to space directory for file validation
            
        Returns:
            List of space content items
        """
        space_content = []
        
        for item in navigation:
            content_item = self.convert_navigation_item(item, space_dir)
            space_content.append(content_item)
        
        return space_content
    
    def convert_navigation_item(
        self, 
        nav_item: Dict[str, Any], 
        space_dir: Path
    ) -> Dict[str, Any]:
        """
        Convert a single navigation item to space content format
        
        Args:
            nav_item: Single navigation item
            space_dir: Path to space directory for file validation
            
        Returns:
            Space content item
        """
        # Determine type based on whether it has children
        item_type = "collection" if nav_item.get("children") else "page"
        
        # Check if HTML file exists
        html_file = space_dir / nav_item["href"]
        html_exists = html_file.exists()
        
        # Extract attachments if any
        attachments = self.find_attachments_for_page(nav_item["href"], space_dir)
        
        content_item = {
            "title": nav_item["title"],
            "html_page": nav_item["href"] if html_exists else None,
            "md_content": "",  # Will be populated later
            "parent_uuid": None,  # Will be set during API upload
            "page_uuid": None,   # Will be set during API upload
            "created": False,
            "type": item_type,
            "attachments": attachments,
            "children": []
        }
        
        # Process children recursively
        for child in nav_item.get("children", []):
            child_item = self.convert_navigation_item(child, space_dir)
            content_item["children"].append(child_item)
        
        return content_item
    
    def find_attachments_for_page(self, html_filename: str, space_dir: Path) -> List[str]:
        """
        Find attachments associated with a page by scanning both directory structure
        and HTML content for attachment references
        
        Args:
            html_filename: Name of the HTML file
            space_dir: Path to space directory
            
        Returns:
            List of attachment file paths
        """
        attachments = []
        
        # Check for attachments directory
        attachments_dir = space_dir / "attachments"
        if not attachments_dir.exists():
            return attachments
        
        # Extract page ID from filename for matching
        page_id_match = re.search(r'(\d{8,})', html_filename)
        if not page_id_match:
            return attachments
        
        page_id = page_id_match.group(1)
        
        # Method 1: Look for page-specific attachment directory
        page_attachment_dir = attachments_dir / page_id
        if page_attachment_dir.exists() and page_attachment_dir.is_dir():
            for attachment_file in page_attachment_dir.glob("*"):
                if attachment_file.is_file():
                    relative_path = f"attachments/{page_id}/{attachment_file.name}"
                    attachments.append(relative_path)
        
        # Method 2: Parse HTML content for attachment references
        html_file = space_dir / html_filename
        if html_file.exists():
            with open(html_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            soup = BeautifulSoup(content, 'html.parser')
            
            # Find attachment links in the HTML
            attachment_links = soup.find_all('a', href=re.compile(r'attachments/'))
            for link in attachment_links:
                # Type check to ensure we have a Tag element
                if isinstance(link, Tag):
                    href = link.get('href')
                    # Type check to ensure href is a string
                    if href and isinstance(href, str) and href.startswith('attachments/'):
                        # Clean up the path
                        attachment_path = href.replace('../', '').replace('./', '')
                        if attachment_path not in attachments:
                            attachments.append(attachment_path)
        
        return attachments
    
    def extract_markdown_content(self, space_key: str) -> bool:
        """
        Extract markdown content for all pages in a space JSON file
        
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
        
        # Get the local folder path
        local_folder = Path(self.base_path / space_data["local_folder"])
        
        # Process all content items
        self._extract_content_recursive(space_data["space_content"], local_folder)
        
        # Update processing stats
        space_data["processing_stats"]["content_extracted_at"] = self.get_current_timestamp()
        
        # Save the updated JSON
        with open(space_file, 'w', encoding='utf-8') as f:
            json.dump(space_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Extracted markdown content for space: {space_key}")
        return True
    
    def _extract_content_recursive(
        self, 
        content_items: List[Dict[str, Any]], 
        local_folder: Path
    ) -> None:
        """
        Recursively extract markdown content for all items
        
        Args:
            content_items: List of content items to process
            local_folder: Path to local folder containing HTML files
        """
        for item in content_items:
            # Extract content for this item
            if item.get("html_page"):
                html_file = local_folder / item["html_page"]
                if html_file.exists():
                    item["md_content"] = self.html_to_markdown(html_file)
                else:
                    self.logger.warning(f"HTML file not found: {html_file}")
                    item["md_content"] = f"# {item['title']}\n\nContent not found."
            else:
                # Create basic content for collections
                item["md_content"] = f"# {item['title']}\n\nThis is a collection page."
            
            # Process children recursively
            if item.get("children"):
                self._extract_content_recursive(item["children"], local_folder)
    
    def html_to_markdown(self, html_file: Path) -> str:
        """
        Convert HTML file to clean markdown without breadcrumbs, titles, or navigation
        
        Args:
            html_file: Path to HTML file
            
        Returns:
            Clean markdown content
        """
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        soup = BeautifulSoup(content, 'html.parser')
        
        # Step 1: Remove all navigation and header elements
        # Remove breadcrumb navigation
        breadcrumb_elements = soup.find_all(['ol', 'nav', 'div'], 
                                          attrs={'id': re.compile(r'breadcrumb|navigation'),
                                                'class': re.compile(r'breadcrumb|navigation')})
        for element in breadcrumb_elements:
            element.decompose()
        
        # Remove the main header section (contains breadcrumbs and title)
        main_header = soup.find('div', id='main-header')
        if main_header:
            main_header.decompose()
        
        # Remove page title elements (multiple patterns)
        title_elements = soup.find_all(['h1', 'h2', 'div'], 
                                     attrs={'id': re.compile(r'title|pagetitle'),
                                           'class': re.compile(r'pagetitle|title-heading')})
        for title in title_elements:
            title.decompose()
        
        # Remove page metadata (created by, modified by, etc.)
        metadata_elements = soup.find_all(['div'], 
                                        attrs={'class': re.compile(r'page-metadata|metadata')})
        for metadata in metadata_elements:
            metadata.decompose()
        
        # Remove footer
        footer = soup.find('div', id='footer')
        if footer:
            footer.decompose()
        
        # Step 2: Focus on the main wiki content
        # Try to find the main content area - prefer the most specific
        main_content = soup.find('div', attrs={'id': 'main-content', 'class': 'wiki-content'})
        
        # Fallback options if the exact match isn't found
        if not main_content:
            main_content = soup.find('div', class_='wiki-content')
        if not main_content:
            main_content = soup.find('div', id='content')
        if not main_content:
            main_content = soup.find('div', id='main')
        if not main_content:
            main_content = soup.find('body')
        
        if main_content and isinstance(main_content, Tag):
            # Step 3: Clean up remaining navigation elements within content
            # Remove any remaining nav elements
            nav_elements = main_content.find_all(['nav', 'div'], 
                                               attrs={'class': re.compile(r'nav|menu|sidebar')})
            for nav in nav_elements:
                if isinstance(nav, Tag):
                    nav.decompose()
            
            # Remove any remaining breadcrumb-like lists at the beginning
            first_ol = main_content.find('ol')
            if first_ol and isinstance(first_ol, Tag):
                # Check if this OL contains a link to index.html (breadcrumb indicator)
                index_link = first_ol.find('a', {'href': 'index.html'})
                if index_link:
                    first_ol.decompose()
            
            # Step 3.5: Clean attachment URLs - strip query parameters and convert to template format
            self._clean_attachment_urls_in_html(main_content)
            
            # Step 4: Convert to markdown
            markdown = self.html2text_converter.handle(str(main_content))
            
            # Step 5: Clean up the markdown
            markdown = self.clean_markdown(markdown)
            
            return markdown.strip()
        
        return f"Could not extract content from {html_file.name}"
    
    def _clean_attachment_urls_in_html(self, soup_element: Tag) -> None:
        """
        Clean attachment URLs in HTML by stripping query parameters and converting to template format
        
        Args:
            soup_element: BeautifulSoup element to process
        """
        import re
        
        # Find all img tags with src attributes containing attachments
        img_elements = soup_element.find_all('img', src=re.compile(r'attachments/'))
        
        # Find all a tags with href attributes containing attachments  
        a_elements = soup_element.find_all('a', href=re.compile(r'attachments/'))
        
        # Process img elements
        for element in img_elements:
            if isinstance(element, Tag):
                url = element.get('src')
                if url and 'attachments/' in url and isinstance(url, str):
                    # Strip query parameters (everything after ?)
                    base_url = url.split('?')[0]
                    
                    # Convert to template format for later UUID replacement
                    template_url = f"{{{base_url}}}"
                    element['src'] = template_url
                    
                    self.logger.debug(f"Converted img src: {url} -> {template_url}")
        
        # Process a elements
        for element in a_elements:
            if isinstance(element, Tag):
                url = element.get('href')
                if url and 'attachments/' in url and isinstance(url, str):
                    # Strip query parameters (everything after ?)
                    base_url = url.split('?')[0]
                    
                    # Convert to template format for later UUID replacement
                    template_url = f"{{{base_url}}}"
                    element['href'] = template_url
                    
                    self.logger.debug(f"Converted a href: {url} -> {template_url}")

    def clean_markdown(self, markdown: str) -> str:
        """
        Clean up markdown content to remove artifacts from HTML conversion
        
        Args:
            markdown: Raw markdown content
            
        Returns:
            Cleaned markdown content
        """
        # Remove any remaining breadcrumb patterns at the start
        # Pattern: "1. [Page](link)" type lists at beginning
        lines = markdown.split('\n')
        cleaned_lines = []
        skip_breadcrumb = True
        
        for line in lines:
            stripped = line.strip()
            
            # Skip initial breadcrumb-like numbered lists
            if skip_breadcrumb:
                if (re.match(r'^\d+\.\s*\[.*?\]\(.*?\)\s*$', stripped) or
                    stripped == '' or
                    re.match(r'^\d+\.\s*$', stripped)):
                    continue  # Skip this line
                else:
                    skip_breadcrumb = False  # Start keeping content
            
            cleaned_lines.append(line)
        
        markdown = '\n'.join(cleaned_lines)
        
        # Remove excessive whitespace
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        
        # Remove empty list items
        markdown = re.sub(r'^\s*[\*\-\+]\s*$', '', markdown, flags=re.MULTILINE)
        
        # Clean up table formatting
        markdown = re.sub(r'\|\s*\|', '|', markdown)
        
        # Remove standalone "Created by... modified by..." lines
        markdown = re.sub(r'^Created by.*?modified.*?on.*?$', '', markdown, flags=re.MULTILINE)
        
        # Remove document generation footer
        markdown = re.sub(r'^Document generated by Confluence.*?$', '', markdown, flags=re.MULTILINE)
        
        # Clean up multiple consecutive blank lines again after all removals
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        
        return markdown
    
    def get_current_timestamp(self) -> str:
        """Get current timestamp as ISO string"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def list_available_spaces(self) -> List[str]:
        """
        List all available space JSON files
        
        Returns:
            List of space keys that have JSON files
        """
        space_files = list(self.output_dir.glob("*.json"))
        return [f.stem for f in space_files]
    
    def get_space_summary(self, space_key: str) -> Optional[Dict[str, Any]]:
        """
        Get summary information about a space
        
        Args:
            space_key: Space key to summarize
            
        Returns:
            Summary information or None if not found
        """
        space_file = self.output_dir / f"{space_key}.json"
        if not space_file.exists():
            return None
        
        with open(space_file, 'r', encoding='utf-8') as f:
            space_data = json.load(f)
        
        def count_items(items):
            count = len(items)
            for item in items:
                count += count_items(item.get('children', []))
            return count
        
        total_items = count_items(space_data["space_content"])
        
        return {
            "space_name": space_data["space_name"],
            "space_key": space_data["space_key"],
            "description": space_data.get("description", ""),
            "total_items": total_items,
            "root_items": len(space_data["space_content"]),
            "processing_stats": space_data.get("processing_stats", {}),
            "file_path": str(space_file)
        }


def main():
    """Test the SpaceProcessor"""
    
    base_path = Path("/Users/rion/VSCode/IS")
    processor = SpaceProcessor(base_path)
    
    print("=== PROCESSING INPUT DIRECTORIES ===")
    processed_spaces = processor.process_input_directories()
    print(f"Processed spaces: {processed_spaces}")
    
    print("\n=== AVAILABLE SPACES ===")
    available_spaces = processor.list_available_spaces()
    for space_key in available_spaces:
        summary = processor.get_space_summary(space_key)
        if summary:
            print(f"{space_key}: {summary['space_name']} ({summary['total_items']} items)")
    
    # Extract markdown content for the first space
    if available_spaces:
        first_space = available_spaces[0]
        print(f"\n=== EXTRACTING CONTENT FOR {first_space.upper()} ===")
        success = processor.extract_markdown_content(first_space)
        print(f"Content extraction successful: {success}")


if __name__ == "__main__":
    main()