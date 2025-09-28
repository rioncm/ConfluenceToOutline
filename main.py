#! venv/bin/python3
"""
Main CLI Interface for the new SpaceProcessor workflow
Implements the clean architecture approach for Confluence space processing
"""

import argparse
import sys
from pathlib import Path
import os
import dotenv
from libs.space_processor import SpaceProcessor
from libs.api_upload_manager import ApiUploadManager
from libs.zip_extractor import ZipExtractor
from libs.config import AppConfig
from libs.logger import setup_logging

# Load environment variables from .env file
dotenv.load_dotenv('.env')


def cmd_extract_zips(args):
    """Extract ZIP files from zips/ directory to input/ directory"""
    config = AppConfig.from_args(args)
    
    # Set up logging
    logger = setup_logging(config.logging.log_level, config.logging.log_file)
    logger.info(f"Starting ZIP extraction with log level: {config.logging.get_level_name()}")
    
    base_path = Path(args.base_path)
    
    print("=== EXTRACTING ZIP FILES ===")
    print(f"Source: {config.directories.zips_dir}")
    print(f"Target: {config.directories.input_dir}")
    
    zips_path = base_path / config.directories.zips_dir
    if not zips_path.exists():
        print(f"❌ ZIP directory not found: {zips_path}")
        return 1
    
    # Create ZipExtractor with config
    extractor = ZipExtractor(
        zips_directory=str(zips_path),
        input_directory=str(base_path / config.directories.input_dir),
        security_config=config.security
    )
    
    results = extractor.extract_all_zips()
    
    if results['successful_extractions'] > 0:
        print(f"\n🎉 Ready for next phase:")
        print(f"   python main.py process-input")
        return 0
    else:
        return 1


def cmd_process_input(args):
    """Process input directories and create space JSON files"""
    config = AppConfig.from_args(args)
    
    # Set up logging
    logger = setup_logging(config.logging.log_level, config.logging.log_file)
    logger.info(f"Starting input processing with log level: {config.logging.get_level_name()}")
    
    processor = SpaceProcessor(Path(args.base_path))
    
    print("=== PROCESSING INPUT DIRECTORIES ===")
    processed_spaces = processor.process_input_directories()
    
    if processed_spaces:
        print(f"✅ Successfully processed {len(processed_spaces)} spaces:")
        for space_key in processed_spaces:
            summary = processor.get_space_summary(space_key)
            if summary:
                print(f"  - {space_key}: {summary['space_name']} ({summary['total_items']} items)")
        
        print(f"\n📁 JSON files created in: {processor.output_dir}")
        print("ℹ️  Review and edit these files before uploading to the API")
    else:
        print("❌ No spaces were processed")
        return 1
    
    return 0


def cmd_extract_content(args):
    """Extract markdown content for specified spaces"""
    config = AppConfig.from_args(args)
    
    # Set up logging
    logger = setup_logging(config.logging.log_level, config.logging.log_file)
    logger.info(f"Starting content extraction with log level: {config.logging.get_level_name()}")
    
    processor = SpaceProcessor(Path(args.base_path))
    
    # Get list of spaces to process
    if args.spaces:
        spaces_to_process = args.spaces
    else:
        # Process all available spaces
        spaces_to_process = processor.list_available_spaces()
    
    if not spaces_to_process:
        print("❌ No spaces found to process")
        return 1
    
    print(f"=== EXTRACTING CONTENT FOR {len(spaces_to_process)} SPACES ===")
    
    success_count = 0
    for space_key in spaces_to_process:
        print(f"📄 Processing {space_key}...")
        success = processor.extract_markdown_content(space_key)
        if success:
            success_count += 1
            print(f"  ✅ {space_key} - Content extracted successfully")
        else:
            print(f"  ❌ {space_key} - Failed to extract content")
    
    print(f"\n✅ Successfully processed {success_count}/{len(spaces_to_process)} spaces")
    return 0 if success_count > 0 else 1


def cmd_api_upload(args):
    """Upload spaces to API"""
    config = AppConfig.from_args(args)
    
    # Set up logging FIRST
    logger = setup_logging(config.logging.log_level, config.logging.log_file)
    logger.info(f"Starting API upload with log level: {config.logging.get_level_name()}")
    logger.debug(f"Configuration: {config.to_dict()}")
    
    # Override config with command line arguments if provided
    if args.api_url:
        config.api.api_url = args.api_url
    if args.api_token:
        config.api.api_key = args.api_token
    
    # Validate API configuration
    if not config.api.api_url or not config.api.api_key:
        print("❌ API URL and token required. Set via --api-url/--api-token or environment variables:")
        print("   OUTLINE_API_URL and OUTLINE_API_TOKEN")
        return 1
    
    manager = ApiUploadManager(Path(args.base_path), config.api.api_url, config.api.api_key)
    
    # Get list of spaces to upload
    if args.spaces:
        spaces_to_upload = args.spaces
    else:
        print("❌ Please specify space keys to upload with --spaces")
        return 1
    
    print(f"=== UPLOADING {len(spaces_to_upload)} SPACES TO API ===")
    
    success_count = 0
    for space_key in spaces_to_upload:
        print(f"🚀 Uploading {space_key}...")
        success = manager.upload_space(space_key)
        if success:
            success_count += 1
            print(f"  ✅ {space_key} - Upload successful")
        else:
            print(f"  ❌ {space_key} - Upload failed")
    
    print(f"\n✅ Successfully uploaded {success_count}/{len(spaces_to_upload)} spaces")
    return 0 if success_count > 0 else 1


def cmd_status(args):
    """Show status of spaces"""
    config = AppConfig.from_args(args)
    processor = SpaceProcessor(Path(args.base_path))
    available_spaces = processor.list_available_spaces()
    
    if not available_spaces:
        print("❌ No spaces found")
        return 1
    
    print("=== SPACE STATUS ===")
    
    # Try to create API manager for upload status (if credentials available)
    api_manager = None
    
    # Override config with command line arguments if provided
    if args.api_url:
        config.api.api_url = args.api_url
    if args.api_token:
        config.api.api_key = args.api_token
    
    if config.api.api_url and config.api.api_key:
        api_manager = ApiUploadManager(Path(args.base_path), config.api.api_url, config.api.api_key)
    
    for space_key in available_spaces:
        summary = processor.get_space_summary(space_key)
        if summary:
            print(f"\n📚 {space_key.upper()}: {summary['space_name']}")
            print(f"   📄 Items: {summary['total_items']} total, {summary['root_items']} root")
            
            stats = summary.get('processing_stats', {})
            if stats.get('processed_at'):
                print(f"   ⏱️  Processed: {stats['processed_at'][:19].replace('T', ' ')}")
            if stats.get('content_extracted_at'):
                print(f"   📝 Content extracted: {stats['content_extracted_at'][:19].replace('T', ' ')}")
            
            # Show upload status if API manager available
            if api_manager:
                upload_status = api_manager.get_upload_status(space_key)
                if upload_status:
                    completion = upload_status['completion_percentage']
                    print(f"   🚀 Upload: {upload_status['created_items']}/{upload_status['total_items']} items ({completion:.1f}%)")
                    
                    # Show attachment statistics if available
                    attachment_stats = upload_status.get('attachment_stats', {})
                    if attachment_stats.get('total_attachments', 0) > 0:
                        total_att = attachment_stats['total_attachments']
                        uploaded_att = attachment_stats['uploaded_attachments']
                        failed_att = attachment_stats['failed_attachments']
                        print(f"   📎 Attachments: {uploaded_att}/{total_att} uploaded", end="")
                        if failed_att > 0:
                            print(f", {failed_att} failed")
                        else:
                            print("")
    
    return 0


def cmd_reset(args):
    """Reset upload status for spaces"""
    if not args.spaces:
        print("❌ Please specify space keys to reset with --spaces")
        return 1
    
    config = AppConfig.from_args(args)
    
    # Override config with command line arguments if provided  
    if args.api_url:
        config.api.api_url = args.api_url
    if args.api_token:
        config.api.api_key = args.api_token
    
    # Use placeholder values if no API credentials (reset is local operation)
    api_url = config.api.api_url or "https://placeholder.com/api"
    api_token = config.api.api_key or "placeholder-token"
    
    manager = ApiUploadManager(Path(args.base_path), api_url, api_token)
    
    print(f"=== RESETTING UPLOAD STATUS FOR {len(args.spaces)} SPACES ===")
    
    success_count = 0
    for space_key in args.spaces:
        success = manager.reset_upload_status(space_key)
        if success:
            success_count += 1
            print(f"  ✅ {space_key} - Reset successful")
        else:
            print(f"  ❌ {space_key} - Reset failed")
    
    print(f"\n✅ Successfully reset {success_count}/{len(args.spaces)} spaces")
    return 0 if success_count > 0 else 1


def cmd_point_zero(args):
    """Reset local directories to clean state while preserving ZIP files"""
    import shutil
    
    print("=" * 60)
    print("POINT ZERO: RESETTING LOCAL DIRECTORIES")
    print("=" * 60)
    print("This will remove all extracted and processed files while preserving:")
    print("  ✅ ZIP files (zips/ directory)")
    print("  ✅ API data (Outline remains unchanged)")
    print("  ❌ Extracted files (input/ directory)")
    print("  ❌ Processed files (output/ directory)")
    print()
    
    # Get confirmation
    confirm = input("Are you sure you want to proceed? (yes/no): ").lower().strip()
    if confirm not in ['yes', 'y']:
        print("❌ Reset cancelled.")
        return 1
    
    base_path = Path(args.base_path)
    input_dir = base_path / 'input'
    output_dir = base_path / 'output'
    
    removed_count = 0
    
    # Remove input directory contents (but keep the directory and .gitkeep)
    if input_dir.exists():
        print(f"🧹 Cleaning input directory: {input_dir}")
        for item in input_dir.iterdir():
            if item.name != '.gitkeep':
                if item.is_dir():
                    shutil.rmtree(item)
                    print(f"   🗑️  Removed directory: {item.name}")
                    removed_count += 1
                else:
                    item.unlink()
                    print(f"   🗑️  Removed file: {item.name}")
                    removed_count += 1
    
    # Remove output directory contents (but keep the directory and .gitkeep)
    if output_dir.exists():
        print(f"🧹 Cleaning output directory: {output_dir}")
        for item in output_dir.iterdir():
            if item.name != '.gitkeep':
                if item.is_dir():
                    shutil.rmtree(item)
                    print(f"   🗑️  Removed directory: {item.name}")
                    removed_count += 1
                else:
                    item.unlink()
                    print(f"   🗑️  Removed file: {item.name}")
                    removed_count += 1
    
    print("-" * 60)
    print(f"✅ Point Zero Complete!")
    print(f"   Removed {removed_count} items")
    print(f"   ZIP files preserved in zips/ directory")
    print(f"   Ready to run: python main.py process-input")
    print("=" * 60)
    
    return 0


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Clean Confluence Space Processor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract ZIP files from zips/ directory
  python main.py extract-zips
  
  # Process input directories and create JSON files
  python main.py process-input
  
  # Extract markdown content for all spaces
  python main.py extract-content
  
  # Extract content for specific spaces
  python main.py extract-content --spaces is gi
  
  # Upload specific spaces to API
  python main.py api-upload --spaces is gi
  
  # Show status of all spaces
  python main.py status
  
  # Reset upload status
  python main.py reset --spaces is gi
  
  # Reset local directories (preserves ZIP files)
  python main.py point-zero

Complete Workflow:
  1. python main.py extract-zips      # Extract ZIP exports
  2. python main.py process-input     # Parse structure from HTML
  3. python main.py extract-content   # Convert to markdown
  4. python main.py api-upload --spaces is gi  # Upload to Outline

Environment Variables:
  OUTLINE_API_URL    - Base URL for Outline API
  OUTLINE_API_TOKEN  - API token for authentication
        """
    )
    
    parser.add_argument(
        '--base-path',
        default='.',
        help='Base path for the project (default: current directory)'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Extract ZIP files command (Phase 0)
    extract_parser = subparsers.add_parser(
        'extract-zips',
        help='Extract ZIP files from zips/ directory to input/ directory'
    )
    extract_parser.add_argument(
        '--zips-dir',
        default='zips',
        help='Directory containing ZIP files to extract (default: zips)'
    )
    extract_parser.add_argument(
        '--input-dir', 
        default='input',
        help='Target directory for extracted files (default: input)'
    )
    
    # Process input command
    process_parser = subparsers.add_parser(
        'process-input',
        help='Process input directories and create space JSON files'
    )
    
    # Extract content command
    extract_parser = subparsers.add_parser(
        'extract-content',
        help='Extract markdown content from HTML files'
    )
    extract_parser.add_argument(
        '--spaces',
        nargs='+',
        help='Space keys to process (default: all available)'
    )
    
    # API upload command
    upload_parser = subparsers.add_parser(
        'api-upload',
        help='Upload spaces to Outline API'
    )
    upload_parser.add_argument(
        '--spaces',
        nargs='+',
        required=True,
        help='Space keys to upload (required)'
    )
    upload_parser.add_argument(
        '--api-url',
        help='Outline API base URL (or set OUTLINE_API_URL env var)'
    )
    upload_parser.add_argument(
        '--api-token',
        help='Outline API token (or set OUTLINE_API_TOKEN env var)'
    )
    
    # Status command
    status_parser = subparsers.add_parser(
        'status',
        help='Show status of all spaces'
    )
    status_parser.add_argument(
        '--api-url',
        help='Outline API base URL for upload status (optional)'
    )
    status_parser.add_argument(
        '--api-token',
        help='Outline API token for upload status (optional)'
    )
    
    # Reset command
    reset_parser = subparsers.add_parser(
        'reset',
        help='Reset upload status for spaces'
    )
    reset_parser.add_argument(
        '--spaces',
        nargs='+',
        required=True,
        help='Space keys to reset (required)'
    )
    reset_parser.add_argument(
        '--api-url',
        help='API URL (optional, placeholder if not provided)'
    )
    reset_parser.add_argument(
        '--api-token',
        help='API token (optional, placeholder if not provided)'
    )
    
    # Point Zero command
    point_zero_parser = subparsers.add_parser(
        'point-zero',
        help='Reset local directories to clean state (preserves ZIP files)'
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Dispatch to command handlers
    command_handlers = {
        'extract-zips': cmd_extract_zips,
        'process-input': cmd_process_input,
        'extract-content': cmd_extract_content,
        'api-upload': cmd_api_upload,
        'status': cmd_status,
        'reset': cmd_reset,
        'point-zero': cmd_point_zero
    }
    
    handler = command_handlers.get(args.command)
    if handler:
        try:
            return handler(args)
        except KeyboardInterrupt:
            print("\n❌ Operation cancelled by user")
            return 1
        except Exception as e:
            print(f"❌ Error: {e}")
            return 1
    else:
        print(f"❌ Unknown command: {args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())