import zipfile
import os
from pathlib import Path
from typing import List, Dict, Any
import shutil

import zipfile
import os
from pathlib import Path
from typing import List, Dict, Any
import shutil
from .logger import get_logger


class ZipExtractor:
    """
    Handles extraction of Confluence export zip files to structured input directories.
    """
    
    def __init__(self, zips_directory: str = "zips", input_directory: str = "input", security_config=None):
        """
        Initialize the zip extractor.
        
        Args:
            zips_directory: Directory containing zip files to extract
            input_directory: Base directory for extracted content
            security_config: SecurityConfig object for limits (optional)
        """
        self.zips_directory = Path(zips_directory)
        self.input_directory = Path(input_directory)
        self.logger = get_logger('zip_extractor')
        
        # Use security config if provided, otherwise use defaults
        if security_config:
            self.max_file_size = security_config.max_file_size
            self.max_total_size = security_config.max_total_size
            self.max_files = security_config.max_files
        else:
            # Fallback defaults
            self.max_file_size = 100 * 1024 * 1024  # 100MB per file
            self.max_total_size = 1024 * 1024 * 1024  # 1GB total extraction
            self.max_files = 10000  # Maximum files per archive
        
        # Ensure input directory exists
        self.input_directory.mkdir(exist_ok=True)
        self.logger.debug(f"Initialized ZipExtractor - zips: {self.zips_directory}, input: {self.input_directory}")
    
    def get_zip_files(self) -> List[Path]:
        """
        Get all zip files in the zips directory.
        
        Returns:
            List of zip file paths
        """
        if not self.zips_directory.exists():
            return []
        
        return list(self.zips_directory.glob("*.zip"))
    
    def extract_zip_name(self, zip_path: Path) -> str:
        """
        Extract a clean folder name from zip filename.
        
        Args:
            zip_path: Path to the zip file
            
        Returns:
            Clean folder name for extraction
        """
        # Remove .zip extension
        base_name = zip_path.stem
        
        # Clean up common Confluence export naming patterns
        # e.g., "Confluence-space-export-135853.html.zip" -> "Confluence-space-export"
        if base_name.endswith('.html'):
            base_name = base_name[:-5]  # Remove .html
        
        # Replace common patterns
        base_name = base_name.replace('Confluence-space-export-', 'Export-')
        
        # Clean up for filesystem safety
        base_name = base_name.replace(' ', '-')
        base_name = ''.join(c for c in base_name if c.isalnum() or c in '-_')
        
        return base_name
    
    def safe_extract_member(self, zip_ref: zipfile.ZipFile, member: zipfile.ZipInfo, output_dir: Path) -> bool:
        """
        Safely extract a single zip member with security checks.
        
        Args:
            zip_ref: Open ZipFile object
            member: ZipInfo object for the member to extract
            output_dir: Output directory path
            
        Returns:
            True if extraction successful, False if blocked for security
        """
        # Security check: Prevent directory traversal
        if os.path.isabs(member.filename) or ".." in member.filename:
            print(f"⚠️  Blocked suspicious path: {member.filename}")
            return False
        
        # Security check: Prevent zip bombs (large files)
        if member.file_size > self.max_file_size:
            self.logger.warning(f"Blocked large file ({member.file_size} bytes): {member.filename}")
            print(f"⚠️  Blocked large file ({member.file_size} bytes): {member.filename}")
            return False
        
        # Security check: Prevent excessively long paths
        if len(member.filename) > 255:
            print(f"⚠️  Blocked long filename: {member.filename[:50]}...")
            return False
        
        try:
            zip_ref.extract(member, output_dir)
            return True
        except Exception as e:
            print(f"⚠️  Failed to extract {member.filename}: {e}")
            return False
    
    def extract_single_zip(self, zip_path: Path) -> Dict[str, Any]:
        """
        Extract a single zip file to the input directory.
        
        Args:
            zip_path: Path to the zip file to extract
            
        Returns:
            Dictionary with extraction results
        """
        folder_name = self.extract_zip_name(zip_path)
        output_dir = self.input_directory / folder_name
        
        result = {
            'zip_file': str(zip_path),
            'folder_name': folder_name,
            'output_dir': str(output_dir),
            'success': False,
            'files_extracted': 0,
            'error': None
        }
        
        try:
            # Remove existing output directory if it exists
            if output_dir.exists():
                print(f"Removing existing directory: {output_dir}")
                shutil.rmtree(output_dir)
            
            # Create output directory
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Extract zip file with security checks
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Get list of files to extract
                file_list = zip_ref.namelist()
                
                # Security check: Too many files (zip bomb protection)
                if len(file_list) > self.max_files:
                    result['error'] = f"Archive contains too many files ({len(file_list)} > {self.max_files})"
                    self.logger.error(f"{zip_path.name} contains too many files: {len(file_list)}")
                    print(f"❌ Error: {zip_path.name} contains too many files")
                    return result
                
                # Security check: Total uncompressed size
                total_size = sum(info.file_size for info in zip_ref.infolist())
                if total_size > self.max_total_size:
                    result['error'] = f"Archive too large when uncompressed ({total_size} bytes)"
                    self.logger.error(f"{zip_path.name} is too large when uncompressed: {total_size} bytes")
                    print(f"❌ Error: {zip_path.name} is too large when uncompressed")
                    return result
                
                # Extract files with security checks
                extracted_count = 0
                blocked_count = 0
                
                for member in zip_ref.infolist():
                    if self.safe_extract_member(zip_ref, member, output_dir):
                        extracted_count += 1
                    else:
                        blocked_count += 1
                
                result['files_extracted'] = extracted_count
                result['files_blocked'] = blocked_count
                result['success'] = True
                
                if blocked_count > 0:
                    print(f"✅ Extracted {extracted_count} files from {zip_path.name} to {folder_name}/ (blocked {blocked_count} suspicious files)")
                else:
                    print(f"✅ Extracted {extracted_count} files from {zip_path.name} to {folder_name}/")
                
        except zipfile.BadZipFile:
            result['error'] = "Invalid or corrupted zip file"
            print(f"❌ Error: {zip_path.name} is not a valid zip file")
            
        except PermissionError as e:
            result['error'] = f"Permission denied: {str(e)}"
            print(f"❌ Error: Permission denied extracting {zip_path.name}")
            
        except Exception as e:
            result['error'] = str(e)
            print(f"❌ Error extracting {zip_path.name}: {str(e)}")
        
        return result
    
    def extract_all_zips(self) -> Dict[str, Any]:
        """
        Extract all zip files in the zips directory.
        
        Returns:
            Summary of extraction results
        """
        zip_files = self.get_zip_files()
        
        if not zip_files:
            print("No zip files found in zips/ directory")
            return {
                'total_zips': 0,
                'successful_extractions': 0,
                'failed_extractions': 0,
                'results': []
            }
        
        print(f"Found {len(zip_files)} zip file(s) to extract...")
        print(f"Extracting to: {self.input_directory}")
        print("-" * 50)
        
        results = []
        successful = 0
        failed = 0
        
        for zip_path in zip_files:
            result = self.extract_single_zip(zip_path)
            results.append(result)
            
            if result['success']:
                successful += 1
            else:
                failed += 1
        
        print("-" * 50)
        print(f"Extraction complete!")
        print(f"✅ Successful: {successful}")
        print(f"❌ Failed: {failed}")
        print(f"📁 Output directory: {self.input_directory}")
        
        return {
            'total_zips': len(zip_files),
            'successful_extractions': successful,
            'failed_extractions': failed,
            'results': results
        }
    
    def list_input_directories(self) -> List[str]:
        """
        List all directories in the input folder (extracted projects).
        
        Returns:
            List of directory names in input folder
        """
        if not self.input_directory.exists():
            return []
        
        return [d.name for d in self.input_directory.iterdir() if d.is_dir()]