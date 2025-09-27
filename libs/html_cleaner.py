import html2text
import re
import pathlib
from typing import Dict, List, Optional, Union, Any
import json
from tqdm import tqdm
from .patterns import ConfluencePatterns, HTMLCleaningPatterns
from .logger import get_logger


class ConfluenceHTMLCleaner:
    def __init__(self, preserve_breadcrumbs: bool = True, preserve_titles: bool = True):
        """
        Initialize the HTML cleaner for Confluence exports.
        
        Args:
            preserve_breadcrumbs: Whether to preserve numbered navigation lists
            preserve_titles: Whether to preserve title structure
        """
        self.converter = html2text.HTML2Text()
        self.converter.ignore_links = False
        self.converter.body_width = 0  # Don't wrap lines
        self.converter.unicode_snob = True  # Use unicode characters
        self.converter.emphasis_mark = '_'  # Use underscores for emphasis
        self.converter.strong_mark = '**'   # Use double asterisks for bold
        self.preserve_breadcrumbs = preserve_breadcrumbs
        self.preserve_titles = preserve_titles
        self.logger = get_logger('html_cleaner')
    
    def extract_breadcrumb_navigation_from_soup(self, soup) -> str:
        """
        Extract breadcrumb navigation from BeautifulSoup object.
        
        Args:
            soup: BeautifulSoup parsed HTML object
            
        Returns:
            Formatted breadcrumb navigation as markdown
        """
        if not self.preserve_breadcrumbs:
            return ""
        
        # Find the breadcrumb section
        breadcrumbs = soup.find('ol', {'id': 'breadcrumbs'})
        if not breadcrumbs:
            return ""
        
        # Extract breadcrumb items
        breadcrumb_lines = []
        for i, li in enumerate(breadcrumbs.find_all('li'), 1):
            link = li.find('a')
            if link:
                title = link.get_text().strip()
                href = link.get('href', '')
                breadcrumb_lines.append(f"{i}.  [{title}]({href})")
        
        return '\n'.join(breadcrumb_lines)
    
    def extract_confluence_title_from_soup(self, soup) -> str:
        """
        Extract the page title from BeautifulSoup object.
        
        Args:
            soup: BeautifulSoup parsed HTML object
            
        Returns:
            Clean title text
        """
        if not self.preserve_titles:
            return ""
        
        # Look for the title span
        title_span = soup.find('span', {'id': 'title-text'})
        if title_span:
            title = title_span.get_text().strip()
            # Clean up title - remove "Information Systems :" prefix if present
            title = re.sub(r'^Information\s+Systems\s*:\s*', '', title, flags=re.IGNORECASE)
            return title
        
        # Fallback to HTML title tag
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text().strip()
            title = re.sub(r'^Information\s+Systems\s*:\s*', '', title, flags=re.IGNORECASE)
            return title
        
        return ""
    
    def extract_breadcrumb_navigation_markdown(self, content: str) -> str:
        """
        Extract the numbered navigation list from markdown content.
        
        Args:
            content: Raw markdown content
            
        Returns:
            The breadcrumb navigation section
        """
        if not self.preserve_breadcrumbs:
            return ""
        
        # Look for numbered list at the beginning (handles multi-line links)
        breadcrumb_pattern = r'^((?:\d+\.\s+\[.*?\](?:\([^)]+\)|\n\s+[^)]*\([^)]+\))\s*\n?)+)'
        match = re.search(breadcrumb_pattern, content, re.MULTILINE | re.DOTALL)
        
        if match:
            return match.group(1).strip()
        return ""
    
    def extract_confluence_title_markdown(self, content: str) -> str:
        """
        Extract the page title from markdown-style title markup.
        
        Args:
            content: Raw markdown content
            
        Returns:
            Clean title text
        """
        if not self.preserve_titles:
            return ""
        
        # Look for Confluence title pattern
        title_patterns = [
            r'#\s*<span[^>]*id="title-text"[^>]*>\s*([^<]+)\s*</span>',
            r'#\s*<span[^>]*>\s*Information Systems\s*:\s*([^<]+)\s*</span>',
            r'#\s+(.+?)(?:\s*{[^}]*})?$'  # Fallback for markdown headers
        ]
        
        for pattern in title_patterns:
            match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
            if match:
                title = match.group(1).strip()
                # Clean up title - remove "Information Systems :" prefix if present
                title = re.sub(r'^Information\s+Systems\s*:\s*', '', title, flags=re.IGNORECASE)
                return title
        
        return ""
    
    def clean_confluence_specific_soup(self, soup) -> None:
        """
        Pre-process BeautifulSoup object to handle Confluence-specific HTML.
        Modifies the soup object in place for efficiency.
        
        Args:
            soup: BeautifulSoup object to clean (modified in place)
        """
        # Remove the breadcrumb section to avoid duplication
        breadcrumb_section = soup.find('div', {'id': 'breadcrumb-section'})
        if breadcrumb_section:
            breadcrumb_section.decompose()
        
        # Remove the title header to avoid duplication
        title_heading = soup.find('h1', {'id': 'title-heading'})
        if title_heading:
            title_heading.decompose()
        
        # Remove page metadata
        page_metadata = soup.find('div', class_='page-metadata')
        if page_metadata:
            page_metadata.decompose()
        
        # Remove Confluence-specific style tags
        for style in soup.find_all('style'):
            style.decompose()
        
        # Remove data attributes from spans and other tags
        for tag in soup.find_all():
            if tag.attrs:
                # Keep only href, src, alt, title attributes
                attrs_to_keep = ['href', 'src', 'alt', 'title']
                tag.attrs = {k: v for k, v in tag.attrs.items() if k in attrs_to_keep}
        
        # Clean up Confluence-specific classes and spans
        for span in soup.find_all('span', class_=re.compile(r'legacy-color-text|author|editor|ng-scope')):
            span.unwrap()
        
        # Remove empty paragraphs and divs
        for p in soup.find_all(['p', 'div']):
            if not p.get_text().strip():
                p.decompose()
        
        # Remove Confluence footer content
        # Look for text containing "Document generated by Confluence"
        for element in soup.find_all(text=re.compile(r'Document generated by Confluence', re.IGNORECASE)):
            # Remove the parent element containing this text
            parent = element.parent
            if parent:
                parent.decompose()
        
        # Remove Atlassian links
        for link in soup.find_all('a', href=re.compile(r'atlassian\.com', re.IGNORECASE)):
            link.decompose()
    
    def detect_content_type(self, content: str) -> str:
        """
        Detect if content is HTML or markdown.
        
        Args:
            content: Raw content
            
        Returns:
            'html' or 'markdown'
        """
        # Simple detection - if it has HTML doctype or common HTML tags, it's HTML
        if re.search(r'<!DOCTYPE html|<html|<head|<body', content, re.IGNORECASE):
            return 'html'
        return 'markdown'
    
    def clean_file(self, file_path: str) -> Dict[str, Union[str, int]]:
        """
        Clean a single HTML/markdown file from Confluence export.
        
        Args:
            file_path: Path to the file to clean
            
        Returns:
            Dictionary with cleaned content and metadata
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_content = f.read()
        except Exception as e:
            return {
                'error': f"Failed to read file: {e}",
                'filename': pathlib.Path(file_path).name
            }
        
        # Detect content type
        content_type = self.detect_content_type(raw_content)
        
        if content_type == 'html':
            # OPTIMIZED: Parse HTML once and reuse
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(raw_content, 'html.parser')
            
            # Extract breadcrumb navigation from parsed soup
            breadcrumb = self.extract_breadcrumb_navigation_from_soup(soup)
            # Extract title from parsed soup  
            title = self.extract_confluence_title_from_soup(soup)
            
            # Clean Confluence-specific elements in place
            self.clean_confluence_specific_soup(soup)
            
            # Convert cleaned soup to markdown
            clean_markdown = self.converter.handle(str(soup))
        else:
            # For markdown files, use the old regex-based approach
            breadcrumb = self.extract_breadcrumb_navigation_markdown(raw_content)
            title = self.extract_confluence_title_markdown(raw_content)
            
            # Convert to clean markdown
            clean_markdown = self.converter.handle(raw_content)
        
        # Post-process the markdown
        clean_markdown = self.post_process_markdown(clean_markdown)
        
        return {
            'filename': pathlib.Path(file_path).name,
            'title': title,
            'breadcrumb': breadcrumb,
            'clean_content': clean_markdown,
            'original_size': len(raw_content),
            'cleaned_size': len(clean_markdown),
            'content_type': content_type
        }
    
    def post_process_markdown(self, markdown: str) -> str:
        """
        Post-process the markdown output from html2text.
        
        Args:
            markdown: Raw markdown from html2text
            
        Returns:
            Cleaned and formatted markdown
        """
        # Remove excessive blank lines
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        
        # Clean up malformed links
        markdown = re.sub(r'\[\s*\]\([^)]*\)', '', markdown)  # Remove empty links
        
        # Remove Confluence footer references (flexible date matching)
        markdown = re.sub(r'Document generated by Confluence on [^\n]*\n*', '', markdown, flags=re.IGNORECASE)
        markdown = re.sub(r'\[Atlassian\]\([^)]*\)\s*', '', markdown, flags=re.IGNORECASE)
        
        # Remove any remaining Confluence metadata patterns
        markdown = re.sub(r'Created by.*?(?=\n\n|\n#|\Z)', '', markdown, flags=re.DOTALL)
        markdown = re.sub(r'last modified by.*?on [^\n]*\n*', '', markdown, flags=re.IGNORECASE)
        
        # Fix spacing around headers
        markdown = re.sub(r'\n(#{1,6}\s)', r'\n\n\1', markdown)
        
        # Clean up trailing whitespace
        lines = [line.rstrip() for line in markdown.split('\n')]
        markdown = '\n'.join(lines)
        
        # Remove trailing empty lines but keep one final newline
        markdown = markdown.rstrip() + '\n' if markdown.strip() else ''
        
        return markdown.strip()
    
    def process_directory(self, input_dir: str, output_dir: Optional[str] = None, 
                         file_pattern: str = "*.md") -> Dict[str, Any]:
        """
        Process all files in a directory.
        
        Args:
            input_dir: Directory containing files to process
            output_dir: Directory to save cleaned files (optional)
            file_pattern: File pattern to match (default: *.md)
            
        Returns:
            Processing results summary
        """
        input_path = pathlib.Path(input_dir)
        if not input_path.exists():
            return {'error': f"Input directory {input_dir} does not exist"}
        
        # Set up output directory
        if output_dir:
            output_path = pathlib.Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
        else:
            output_path = input_path / "cleaned"
            output_path.mkdir(exist_ok=True)
        
        # Find all matching files (search recursively)
        files_to_process = list(input_path.rglob(file_pattern))
        results = {
            'total_files': len(files_to_process),
            'processed': 0,
            'errors': [],
            'files_processed': [],
            'output_directory': str(output_path)
        }
        
        for file_path in tqdm(files_to_process, desc="Processing HTML files", unit="file"):
            # Clean the file
            cleaned_data = self.clean_file(str(file_path))
            
            if 'error' in cleaned_data:
                self.logger.error(f"Failed to clean {file_path.name}: {cleaned_data['error']}")
                results['errors'].append({
                    'file': file_path.name,
                    'error': cleaned_data['error']
                })
                continue
            
            # Write cleaned file
            try:
                # Calculate relative path from input to maintain directory structure
                relative_path = file_path.relative_to(input_path)
                
                # Create output file path with preserved directory structure
                output_file = output_path / f"clean_{relative_path}"
                
                # Ensure parent directories exist
                output_file.parent.mkdir(parents=True, exist_ok=True)
                
                # Create cleaned markdown file
                with open(output_file, 'w', encoding='utf-8') as f:
                    if cleaned_data['breadcrumb']:
                        f.write(str(cleaned_data['breadcrumb']) + '\n\n')
                    
                    if cleaned_data['title']:
                        f.write(f"# {cleaned_data['title']}\n\n")
                    
                    f.write(str(cleaned_data['clean_content']))
                
                results['processed'] += 1
                results['files_processed'].append({
                    'input': file_path.name,
                    'output': output_file.name,
                    'title': str(cleaned_data['title']),
                    'size_reduction': int(cleaned_data['original_size']) - int(cleaned_data['cleaned_size'])
                })
                
            except Exception as e:
                results['errors'].append({
                    'file': file_path.name,
                    'error': f"Failed to write output: {e}"
                })
        
        # Write processing summary
        summary_file = output_path / "processing_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        return results