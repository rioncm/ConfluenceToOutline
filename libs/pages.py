import re
from typing import List, Dict, Optional
import pathlib
import json
import os
import mimetypes
from collections import defaultdict
from .patterns import ConfluencePatterns
from .logger import get_logger


class Pages:
    def __init__(self, pages_directory: str = "../pages", attachments_base_path: str = "../IS/attachments"):
        self.pages_directory = pathlib.Path(pages_directory)
        self.attachments_base_path = pathlib.Path(attachments_base_path)
        self.logger = get_logger('pages')
    
    def parse_location_data(self, markdown_content: str) -> List[Dict[str, str]]:
        """
        Parse the location breadcrumb data from markdown content into an ordered array.
        
        Args:
            markdown_content: The raw markdown content as a string
            
        Returns:
            List of dictionaries with 'title' and 'link' keys, ordered from root to current page
        """
        location_data = []
        
        # Split content into lines and look for the numbered list at the beginning
        lines = markdown_content.strip().split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Look for numbered list items (e.g., "1. [Title](link.html)")
            match = ConfluencePatterns.NUMBERED_LIST_PATTERN.match(line)
            
            if match:
                title = match.group(1)
                link = match.group(2)
                location_data.append({
                    'title': title,
                    'link': link
                })
            else:
                # Check for multi-line numbered list items  
                match = ConfluencePatterns.MULTILINE_START_PATTERN.match(line)
                
                if match:
                    # Start of a multi-line link
                    title_parts = [match.group(1)]
                    i += 1
                    
                    # Continue reading lines until we find the closing bracket and link
                    while i < len(lines):
                        next_line = lines[i].strip()
                        
                        # Check if this line completes the link
                        end_match = ConfluencePatterns.MULTILINE_END_PATTERN.match(next_line)
                        
                        if end_match:
                            title_parts.append(end_match.group(1))
                            title = ' '.join(title_parts).strip()
                            link = end_match.group(2)
                            location_data.append({
                                'title': title,
                                'link': link
                            })
                            break
                        else:
                            # This line is part of the title
                            title_parts.append(next_line)
                        
                        i += 1
                elif line and not line.startswith('#') and location_data:
                    # If we hit a non-numbered line that's not a header and we already have location data,
                    # we've probably reached the end of the breadcrumb
                    break
            
            i += 1
                
        return location_data
    
    def parse_location_data_from_file(self, file_path: str) -> List[Dict[str, str]]:
        """
        Parse location data from a markdown file.
        
        Args:
            file_path: Path to the markdown file
            
        Returns:
            List of dictionaries with 'title' and 'link' keys
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return self.parse_location_data(content)
        except FileNotFoundError:
            print(f"File not found: {file_path}")
            return []
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return []
    
    def get_all_markdown_files(self, pattern: str = "*.md") -> List[str]:
        """
        Get all markdown files in the pages directory, sorted for consistent processing.
        Searches recursively through subdirectories.
        
        Args:
            pattern: File pattern to match (default: *.md)
        
        Returns:
            List of file paths, sorted
        """
        if not self.pages_directory.exists():
            return []
        
        # Use rglob to search recursively through subdirectories
        return sorted([str(f) for f in self.pages_directory.rglob(pattern)])
    
    def extract_space_name_from_index(self, file_path: str) -> str:
        """
        Extract the space name from index.html file.
        Looks for: Name | <SPACE NAME> in markdown table format or processed content.
        
        Args:
            file_path: Path to index.html file
            
        Returns:
            The space name or 'Information Systems' as fallback
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Look for "Name | <SPACE NAME>" pattern in markdown table
            lines = content.split('\n')
            for line in lines:
                if line.strip().startswith('Name |'):
                    # Extract space name after the pipe
                    parts = line.split('|')
                    if len(parts) >= 2:
                        space_name = parts[1].strip()
                        if space_name:
                            return space_name
            
            # Alternative: Look for processed content pattern like "Key | GI ---|--- Name | General Information"
            # This happens when HTML cleaner processes the table
            content_clean = content.replace('\n', ' ').replace('  ', ' ')
            if 'Name |' in content_clean:
                # Find the pattern after "Name |"
                name_index = content_clean.find('Name |')
                if name_index >= 0:
                    after_name = content_clean[name_index + 6:].strip()  # Skip "Name |"
                    # Extract until next section or end
                    words = after_name.split()
                    if words:
                        # Take words until we hit "Description" or "##" or similar
                        space_words = []
                        for word in words:
                            if word in ['Description', '##', 'Available', 'Pages:']:
                                break
                            space_words.append(word)
                        if space_words:
                            return ' '.join(space_words)
            
            # Fallback: return default
            return 'Information Systems'
            
        except Exception as e:
            self.logger.warning(f"Could not extract space name from {file_path}: {e}")
            return 'Information Systems'

    def extract_title_from_content(self, markdown_content: str) -> str:
        """
        Extract the page title from the markdown content.
        Looks for: # <span id="title-text"> Information Systems : TITLE </span> or # Space Name : TITLE
        Returns just the TITLE part without the space prefix.
        
        Args:
            markdown_content: The raw markdown content
            
        Returns:
            The cleaned title or empty string if not found
        """
        lines = markdown_content.strip().split('\n')
        
        for line in lines:
            # First check for clean markdown headers (from cleaned HTML)
            clean_header_match = ConfluencePatterns.CLEAN_HEADER_PATTERN.match(line.strip())
            if clean_header_match:
                title = clean_header_match.group(1).strip()
                # Remove space prefix if present (e.g., "General Information : SMS Opt Policy" -> "SMS Opt Policy")
                if ' : ' in title:
                    title = title.split(' : ', 1)[1]
                return title
            
            # Then check for the original HTML title pattern
            match = ConfluencePatterns.TITLE_SPAN_PATTERN.search(line)
            
            if match:
                title = match.group(1).strip()
                # Remove space prefix if present
                if ' : ' in title:
                    title = title.split(' : ', 1)[1]
                return title
        
        return ""
    
    def clean_content_for_api(self, markdown_content: str) -> str:
        """
        Clean markdown content for API upload by removing breadcrumbs and other artifacts.
        
        Args:
            markdown_content: Raw markdown content with breadcrumbs
            
        Returns:
            Cleaned markdown content ready for API upload
        """
        # First, handle inline breadcrumbs (multiple breadcrumbs on one line)
        # Pattern: 1\. [Link](url) 2\. [Link](url) 3\. [Link](url) # Title # Content
        inline_breadcrumb_pattern = r'^(\d+\\?\.\s*\[.*?\]\([^)]+\)\s*)+'
        
        lines = markdown_content.split('\n')
        processed_lines = []
        
        for line in lines:
            # Check if line starts with inline breadcrumbs
            match = re.match(inline_breadcrumb_pattern, line)
            if match:
                # Remove the breadcrumb part and keep the rest
                breadcrumb_end = match.end()
                remaining = line[breadcrumb_end:].strip()
                if remaining:
                    processed_lines.append(remaining)
                # Skip empty lines that were just breadcrumbs
            else:
                processed_lines.append(line)
        
        # Now do regular line-by-line cleaning
        cleaned_lines = []
        skip_breadcrumbs = True
        header_seen = False
        
        for line in processed_lines:
            # Skip numbered breadcrumb lines at the start (handle both normal and escaped dots)
            breadcrumb_pattern = r'^\d+\\?\.\s*\['
            if skip_breadcrumbs and re.match(breadcrumb_pattern, line.strip()):
                continue
            
            # Skip empty lines at the start until we hit content
            if skip_breadcrumbs and not line.strip():
                continue
                
            # If we hit a non-breadcrumb line, stop skipping
            if skip_breadcrumbs and line.strip() and not re.match(breadcrumb_pattern, line.strip()):
                skip_breadcrumbs = False
            
            # Add the line if we're not skipping breadcrumbs
            if not skip_breadcrumbs:
                # Handle lines that start with duplicate headers but have more content
                if line.strip().startswith('#') and header_seen:
                    # Check if this line starts with the same header as already seen
                    existing_headers = [l.strip() for l in cleaned_lines if l.strip().startswith('#')]
                    line_header_part = line.strip().split('#')[1].strip() if '#' in line.strip() else ''
                    
                    # If this header already exists, extract only the new content after it
                    duplicate_found = False
                    for existing_header in existing_headers:
                        existing_header_part = existing_header.split('#')[1].strip() if '#' in existing_header else ''
                        if line_header_part == existing_header_part:
                            # Found duplicate header, extract content after the duplicate
                            parts = line.strip().split('#')
                            if len(parts) > 2:  # Has content after the duplicate header
                                remaining_content = '#'.join(parts[2:]).strip()
                                if remaining_content:
                                    cleaned_lines.append('# ' + remaining_content)
                            duplicate_found = True
                            break
                    
                    if not duplicate_found:
                        cleaned_lines.append(line)
                        header_seen = True
                else:
                    if line.strip().startswith('#'):
                        header_seen = True
                    cleaned_lines.append(line)
        
        # Join lines and clean up excessive whitespace
        cleaned_content = '\n'.join(cleaned_lines)
        
        # Clean titles in content to remove space prefixes
        # Pattern: # Space Name : Title -> # Title
        title_pattern = r'^(#+)\s*[^:]+\s*:\s*(.+)$'
        lines = cleaned_content.split('\n')
        final_lines = []
        
        for line in lines:
            if line.strip().startswith('#'):
                match = re.match(title_pattern, line.strip())
                if match:
                    header_level = match.group(1)  # # or ## or ###
                    title_part = match.group(2).strip()
                    line = f"{header_level} {title_part}"
            final_lines.append(line)
        
        cleaned_content = '\n'.join(final_lines)
        
        # Remove multiple consecutive empty lines
        cleaned_content = re.sub(r'\n{3,}', '\n\n', cleaned_content)
        
        # Strip leading/trailing whitespace
        return cleaned_content.strip()
    
    def extract_attachments_from_content(self, markdown_content: str, page_id: str) -> List[Dict]:
        """
        Extract attachment information from markdown content and file system.
        
        Args:
            markdown_content: The markdown content to scan for attachments
            page_id: The page ID (extracted from filename) to look for attachments
            
        Returns:
            List of attachment dictionaries with path, mime_type, and size info
        """
        attachments = []
        
        # Look for attachment references in markdown (images, links to attachments)
        attachment_patterns = [
            r'!\s*\[([^\]]*)\]\(([^)]+)\)',  # ![alt](path)
            r'\[([^\]]+)\]\(([^)]+\.(png|jpg|jpeg|gif|pdf|docx?|xlsx?|pptx?|txt|zip|rar))\)',  # [text](file.ext)
            r'src=["\']([^"\']+)["\']',  # src="path"
        ]
        
        found_refs = set()
        for pattern in attachment_patterns:
            matches = re.finditer(pattern, markdown_content, re.IGNORECASE)
            for match in matches:
                # Extract the path (second group for most patterns)
                if len(match.groups()) >= 2:
                    path = match.group(2)
                else:
                    path = match.group(1)
                
                if path and ('attachments/' in path or path.startswith('attachments')):
                    found_refs.add(path)
        
        # Check filesystem for attachments directory matching page ID
        attachment_dir = self.attachments_base_path / page_id
        if attachment_dir.exists():
            for file_path in attachment_dir.iterdir():
                if file_path.is_file():
                    try:
                        # Get file info
                        file_size = file_path.stat().st_size
                        mime_type, _ = mimetypes.guess_type(str(file_path))
                        
                        # Create relative path from attachments base
                        relative_path = file_path.relative_to(self.attachments_base_path.parent)
                        
                        attachments.append({
                            'filename': file_path.name,
                            'local_path': str(file_path),
                            'relative_path': str(relative_path),
                            'mime_type': mime_type or 'application/octet-stream',
                            'size_bytes': file_size,
                            'referenced_in_content': any(file_path.name in ref for ref in found_refs)
                        })
                    except Exception as e:
                        print(f"Warning: Could not process attachment {file_path}: {e}")
        
        return attachments
    
    def extract_page_id_from_filename(self, filename: str) -> str:
        """
        Extract the Confluence page ID from filename.
        
        Args:
            filename: The filename (e.g., "clean_3CX-System-Details_2481520646.html")
            
        Returns:
            Page ID string (e.g., "2481520646") or empty string if not found
        """
        # Remove "clean_" prefix if present
        clean_name = filename.replace('clean_', '')
        
        # Look for pattern: Title_PAGEID.html
        match = re.search(r'_(\d+)\.(html?|md)$', clean_name)
        if match:
            return match.group(1)
        
        # Fallback: if filename is just numbers
        name_without_ext = pathlib.Path(clean_name).stem
        if name_without_ext.isdigit():
            return name_without_ext
            
        return ""
    
    def build_integrated_navigation(self, pages_data: List[Dict], space_name: str = "Information Systems") -> Dict:
        """
        Build an integrated navigation structure with page data embedded.
        This creates a single hierarchical structure for top-down API creation.
        
        Args:
            pages_data: List of page dictionaries with path and content information
            space_name: The detected space name from index.html
            
        Returns:
            Integrated navigation hierarchy with embedded page data
        """
        # Create lookup maps
        pages_by_path = {}  # Maps tuple(path) -> page data
        pages_by_exact_path = {}  # Maps tuple(path + [title]) -> page data
        
        for page in pages_data:
            path = page.get('path', [])
            title = page.get('title', '')
            
            if path:
                # Map by navigation path (for pages at folder level)
                path_key = tuple(path)
                if path_key not in pages_by_path:
                    pages_by_path[path_key] = []
                pages_by_path[path_key].append(page)
                
                # Map by exact path including title (for precise matching)
                if title:
                    exact_path_key = tuple(path + [title])
                    pages_by_exact_path[exact_path_key] = page
            else:
                # Root level pages
                if () not in pages_by_path:
                    pages_by_path[()] = []
                pages_by_path[()].append(page)
        
        # Build tree structure with navigation nodes and folder nodes
        root_children = defaultdict(set)
        all_paths = set()
        
        # Collect navigation paths (folder structure)
        for page in pages_data:
            path = page.get('path', [])
            if path:
                # Add each navigation level
                for i in range(len(path)):
                    segment_path = tuple(path[:i+1])
                    all_paths.add(segment_path)
                    
                    # Track parent-child relationships for navigation
                    if i == 0:
                        root_children[None].add(path[0])
                    else:
                        parent = tuple(path[:i])
                        child = path[i]
                        root_children[parent].add(child)
        
        def build_tree_node(path_tuple: Optional[tuple]) -> List[Dict]:
            """Recursively build tree nodes with embedded page data."""
            children = []
            
            # First add navigation folder children
            for child_name in sorted(root_children.get(path_tuple, [])):
                child_path = path_tuple + (child_name,) if path_tuple else (child_name,)
                
                node = {
                    'title': child_name,
                    'path': list(child_path),
                    'type': 'navigation',  # This is a navigation folder
                    'uuid': None,  # Will be filled in during API creation
                    'children': build_tree_node(child_path),
                    'pages': []  # Pages directly in this navigation folder
                }
                
                # Add any pages that belong as children of this navigation level
                if child_path in pages_by_path:
                    for page in pages_by_path[child_path]:
                        page_node = {
                            'title': page['title'],
                            'path': page['path'] + [page['title']],
                            'type': 'page',
                            'uuid': None,
                            'page_data': {
                                'filename': page['filename'],
                                'page_id': page['page_id'],
                                'content': page['content'],
                                'attachments': page['attachments'],
                                'attachment_count': page['attachment_count'],
                                'file_path': page['file_path']
                            },
                            'children': []  # Pages don't have children
                        }
                        node['children'].append(page_node)  # Add as children, not pages
                
                children.append(node)
            
            return children
        
        # Build the complete integrated structure
        root_structure = build_tree_node(None)
        
        # Add root-level pages (pages with empty path)
        root_pages = []
        if () in pages_by_path:
            for page in pages_by_path[()]:
                page_node = {
                    'title': page['title'],
                    'path': [page['title']],
                    'type': 'page',
                    'uuid': None,
                    'page_data': {
                        'filename': page['filename'],
                        'page_id': page['page_id'],
                        'content': page['content'],
                        'attachments': page['attachments'],
                        'attachment_count': page['attachment_count'],
                        'file_path': page['file_path']
                    },
                    'children': []
                }
                root_pages.append(page_node)
        
        return {
            'root': space_name,
            'navigation': root_structure,
            'root_pages': root_pages,
            'total_navigation_nodes': len(all_paths),
            'total_pages': len(pages_data),
            'total_attachments': sum(page['attachment_count'] for page in pages_data)
        }
    
    def process_all_pages(self, pattern: str = "*.md") -> Dict:
        """
        Process all files and build enhanced structure for API integration.
        
        Args:
            pattern: File pattern to match (default: *.md)
        
        Returns:
            Dictionary with processed page data, attachments, and navigation hierarchy
        """
        all_files = self.get_all_markdown_files(pattern)
        processed_pages = []
        all_paths = []
        
        for file_path in all_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Get location data (skip items 1 and 2, keep 3+)
                location_data = self.parse_location_data(content)
                path = [item['title'] for item in location_data[2:]] if len(location_data) > 2 else []
                all_paths.append(path)
                
                # Extract title
                page_title = self.extract_title_from_content(content)
                
                # Get filename and page ID
                filename = pathlib.Path(file_path).name
                page_id = self.extract_page_id_from_filename(filename)
                
                # Extract attachments for this page
                attachments = self.extract_attachments_from_content(content, page_id) if page_id else []
                
                # Clean content for API by removing breadcrumbs
                cleaned_content = self.clean_content_for_api(content)
                
                processed_pages.append({
                    'filename': filename,
                    'title': page_title,
                    'path': path,
                    'page_id': page_id,
                    'attachments': attachments,
                    'attachment_count': len(attachments),
                    'file_path': str(file_path),
                    'content': cleaned_content
                })
                
            except Exception as e:
                print(f"Error processing {file_path}: {e}")
                continue
        
        # Detect space name from index.html if it exists
        space_name = "Information Systems"  # default
        index_files = [f for f in all_files if pathlib.Path(f).name == 'index.html']
        if index_files:
            space_name = self.extract_space_name_from_index(index_files[0])
        
        # Build integrated navigation structure with embedded page data
        integrated_structure = self.build_integrated_navigation(processed_pages, space_name)
        
        return integrated_structure
    
    def write_processed_data(self, output_file: str = "processed_pages.json", pattern: str = "*.md") -> bool:
        """
        Process all pages and write the results to a JSON file.
        
        Args:
            output_file: Path to the output JSON file
            pattern: File pattern to match (default: *.md)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            import json
            
            processed_data = self.process_all_pages(pattern)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(processed_data, f, indent=2, ensure_ascii=False)
            
            print(f"Successfully wrote {processed_data['total_pages']} pages to {output_file}")
            return True
            
        except Exception as e:
            print(f"Error writing processed data: {e}")
            return False