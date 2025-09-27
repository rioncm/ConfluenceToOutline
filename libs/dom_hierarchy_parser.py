#!/usr/bin/env python3
"""
Simple DOM-based HTML Index Parser for Confluence Export Structure
Extracts all anchor tags and builds hierarchy from DOM structure
"""

import re
from pathlib import Path
from bs4 import BeautifulSoup, Tag
from typing import Dict, List, Optional, Any
import json


class DomHierarchyParser:
    """Parse index.html by extracting all links and using DOM structure for hierarchy"""
    
    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        
    def extract_space_metadata(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract space metadata from the index.html table"""
        metadata = {}
        
        table = soup.find('table')
        if table:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True).rstrip(':')
                    value = cells[1].get_text(strip=True)
                    
                    if key == 'Key':
                        metadata['space_key'] = value
                    elif key == 'Name':
                        metadata['space_name'] = value
                    elif key == 'Description':
                        metadata['description'] = value
                    elif key == 'Created by':
                        metadata['created_by'] = value
                        
        return metadata
    
    def extract_page_id_from_href(self, href: str) -> Optional[str]:
        """Extract page ID from href attribute"""
        if not href:
            return None
            
        match = re.search(r'(\d{8,})(?:\.html)?$', href)
        return match.group(1) if match else None
    
    def extract_all_page_links(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract all page links with hierarchy information from DOM structure"""
        
        all_links = []
        
        # Find all anchor tags with HTML file links
        anchors = soup.find_all('a', href=True)
        html_anchors = [a for a in anchors if a.get('href', '').endswith('.html')]
        
        print(f"Found {len(html_anchors)} HTML file links")
        
        for anchor in html_anchors:
            href = anchor.get('href', '')
            title = anchor.get_text(strip=True)
            
            if not title:  # Skip empty titles
                continue
                
            page_id = self.extract_page_id_from_href(href)
            
            # Calculate hierarchy level by counting parent UL elements
            hierarchy_level = self.get_ul_hierarchy_level(anchor)
            
            # Build the path by walking up the DOM tree
            path = self.build_path_from_dom(anchor, hierarchy_level)
            
            link_data = {
                "title": title,
                "path": path,
                "href": href,
                "page_id": page_id,
                "hierarchy_level": hierarchy_level,
                "uuid": None
            }
            
            all_links.append(link_data)
        
        return all_links
    
    def get_ul_hierarchy_level(self, anchor: Tag) -> int:
        """Count the number of UL ancestors to determine hierarchy level"""
        level = 0
        parent = anchor.parent
        
        while parent and parent.name != 'body':
            if parent.name == 'ul':
                level += 1
            parent = parent.parent
            
        return level
    
    def build_path_from_dom(self, anchor: Tag, max_level: int) -> List[str]:
        """Build the path by finding UL ancestors and their first anchor"""
        path_parts = []
        
        # Start from the anchor and work our way up
        current_ul = anchor.parent
        
        # Walk up to find the UL that contains this anchor
        while current_ul and current_ul.name != 'ul':
            current_ul = current_ul.parent
            
        # Now walk up through UL ancestors to build the path
        ul_ancestors = []
        parent = current_ul
        
        while parent and parent.name != 'body':
            if parent.name == 'ul':
                ul_ancestors.append(parent)
            parent = parent.parent
        
        # Reverse to get top-down order
        ul_ancestors.reverse()
        
        # Build path from UL ancestors
        for i, ul_ancestor in enumerate(ul_ancestors):
            if i == len(ul_ancestors) - 1:
                # This is the UL containing our target anchor
                path_parts.append(anchor.get_text(strip=True))
            else:
                # Find the first anchor in this UL level
                first_anchor = self.find_first_anchor_in_ul(ul_ancestor, ul_ancestors[i+1:])
                if first_anchor:
                    path_parts.append(first_anchor.get_text(strip=True))
        
        return path_parts
    
    def find_first_anchor_in_ul(self, ul_element: Tag, child_uls_to_exclude: List[Tag]) -> Optional[Tag]:
        """Find the first anchor in this UL level, excluding child ULs"""
        
        # Find all anchors in this UL
        anchors = ul_element.find_all('a', href=True)
        
        for anchor in anchors:
            # Check if this anchor is in any of the child ULs we should exclude
            skip_anchor = False
            for child_ul in child_uls_to_exclude:
                if child_ul in anchor.parents:
                    skip_anchor = True
                    break
            
            if not skip_anchor and anchor.get('href', '').endswith('.html'):
                return anchor
        
        return None
    
    def build_hierarchy_from_links(self, links: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Build hierarchical structure from links with paths"""
        
        # Create a map of all items by their full path
        path_map = {}
        for link in links:
            path_key = tuple(link['path'])
            path_map[path_key] = {
                "title": link['title'],
                "path": link['path'][:],
                "page_id": link['page_id'],
                "href": link['href'],
                "uuid": None,
                "children": [],
                "type": "page"
            }
        
        # Build parent-child relationships
        for path_key, item in path_map.items():
            if len(path_key) > 1:
                # Find parent
                parent_path_key = path_key[:-1]
                if parent_path_key in path_map:
                    parent = path_map[parent_path_key]
                    parent['children'].append(item)
                    parent['type'] = 'navigation'
        
        # Return root items (those with path length 1)
        root_items = [item for path_key, item in path_map.items() if len(path_key) == 1]
        
        return root_items
    
    def parse_index_html(self, index_path: Path) -> Dict[str, Any]:
        """Parse index.html using DOM hierarchy approach"""
        
        if not index_path.exists():
            raise FileNotFoundError(f"Index file not found: {index_path}")
            
        with open(index_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f"HTML content length: {len(content)} characters")
        
        # Parse with lxml for better performance
        soup = BeautifulSoup(content, 'lxml')
        
        # Extract metadata
        metadata = self.extract_space_metadata(soup)
        
        # Extract all page links with hierarchy
        links = self.extract_all_page_links(soup)
        print(f"Extracted {len(links)} page links")
        
        # Build hierarchical structure
        navigation = self.build_hierarchy_from_links(links)
        
        # Calculate statistics
        total_pages = sum(1 for link in links if len([l for l in links if l['path'][:-1] == link['path']]) == 0)
        total_nav_nodes = len(links) - total_pages
        max_depth = max(len(link['path']) for link in links) if links else 0
        
        structure = {
            "parsing_approach": "DOM_HIERARCHY_BASED",
            "space_metadata": metadata,
            "root": metadata.get('space_name', 'Unknown Space'),
            "space_key": metadata.get('space_key', ''),
            "description": metadata.get('description', ''),
            "navigation": navigation,
            "stats": {
                "total_links_found": len(links),
                "total_pages": self.count_pages(navigation),
                "total_navigation_nodes": self.count_navigation_nodes(navigation),
                "max_depth": max_depth,
                "unique_paths": len(set(tuple(link['path']) for link in links))
            },
            "debug_info": {
                "first_10_links": [
                    {
                        "title": link['title'],
                        "path": link['path'],
                        "level": link['hierarchy_level'],
                        "href": link['href'][:30]
                    }
                    for link in links[:10]
                ]
            }
        }
        
        return structure
    
    def count_pages(self, navigation: List[Dict[str, Any]]) -> int:
        """Count total number of pages (leaf nodes)"""
        count = 0
        for item in navigation:
            if item.get("type") == "page":
                count += 1
            if item.get("children"):
                count += self.count_pages(item["children"])
        return count
    
    def count_navigation_nodes(self, navigation: List[Dict[str, Any]]) -> int:
        """Count total number of navigation nodes (non-leaf nodes)"""
        count = 0
        for item in navigation:
            if item.get("type") == "navigation":
                count += 1
            if item.get("children"):
                count += self.count_navigation_nodes(item["children"])
        return count


def main():
    """Test the DOM hierarchy parser"""
    
    base_path = Path("/Users/rion/VSCode/IS/input")
    index_path = base_path / "Export-135853" / "IS" / "index.html"
    
    if not index_path.exists():
        print(f"Index file not found: {index_path}")
        return
        
    parser = DomHierarchyParser(base_path)
    
    try:
        structure = parser.parse_index_html(index_path)
        
        print("\n=== SPACE METADATA ===")
        metadata = structure["space_metadata"]
        for key, value in metadata.items():
            print(f"{key}: {value}")
            
        print(f"\n=== STRUCTURE STATS ===")
        stats = structure["stats"]
        for key, value in stats.items():
            print(f"{key}: {value}")
            
        print(f"\n=== DEBUG INFO - FIRST 10 LINKS ===")
        debug_info = structure["debug_info"]
        for i, link in enumerate(debug_info["first_10_links"]):
            path_str = " → ".join(link["path"])
            print(f"{i+1}. Level {link['level']}: {path_str}")
            
        print(f"\n=== NAVIGATION SAMPLE (first 3 root items) ===")
        nav = structure["navigation"]
        for i, item in enumerate(nav[:3]):
            print(f"{i+1}. {item['title']} ({item['type']}) - {len(item['children'])} children")
            
            # Show some children
            for j, child in enumerate(item['children'][:3]):
                print(f"   {j+1}. {child['title']} ({child['type']}) - {len(child['children'])} children")
        
        # Save the complete structure
        output_path = base_path.parent / "structure_from_dom_hierarchy.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(structure, f, indent=2, ensure_ascii=False)
            
        print(f"\n=== COMPLETE STRUCTURE SAVED TO ===")
        print(f"{output_path}")
        
    except Exception as e:
        print(f"Error parsing index.html: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()