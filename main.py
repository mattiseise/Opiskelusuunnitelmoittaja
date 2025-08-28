#!/usr/bin/env python3
"""
Opiskelusuunnitelmoittaja - Study Plan Form Filler
Automated form filling tool for study plans using Chrome WebDriver
"""

import sys
import os
import argparse
import json
from typing import List, Optional

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.logger import setup_logger
from src.browser_manager import BrowserManager
from src.excel_handler import ExcelHandler  
from src.form_filler import FormFiller


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Automated study plan form filler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                          # Interactive mode
  python main.py --sheets 1,3,5          # Fill specific sheets
  python main.py --excel custom.xlsx     # Use custom Excel file
  python main.py --config myconfig.json  # Use custom config file
        """
    )
    
    parser.add_argument(
        '--excel', '-e',
        type=str,
        help='Path to Excel file (overrides config setting)'
    )
    
    parser.add_argument(
        '--sheets', '-s',
        type=str,
        help='Comma-separated sheet numbers to process (e.g., "1,3,5")'
    )
    
    parser.add_argument(
        '--config', '-c',
        type=str,
        default='config.json',
        help='Path to configuration file (default: config.json)'
    )
    
    parser.add_argument(
        '--list-sheets', '-l',
        action='store_true',
        help='List available sheets and exit'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    return parser.parse_args()


def print_banner():
    """Print application banner."""
    print("=" * 60)
    print("  OPISKELUSUUNNITELMOITTAJA - Study Plan Form Filler")
    print("  Chrome WebDriver version")
    print("=" * 60)


def print_chrome_instructions(config: dict):
    """Print Chrome browser setup instructions."""
    browser_config = config.get('browser', {})
    launch_command = browser_config.get('launch_command', 'Chrome launch command not configured')
    
    print("\\n" + "=" * 60)
    print("  IMPORTANT: Chrome Browser Setup Required")
    print("=" * 60)
    print("Before running this script, start Chrome with remote debugging enabled:")
    print()
    print(f"Command: {launch_command}")
    print()
    print("Steps:")
    print("1. Close all Chrome windows")
    print("2. Open Command Prompt as Administrator")
    print("3. Run the command above")
    print("4. Chrome will open - navigate to your form page")
    print("5. Run this script")
    print("=" * 60)


def main():
    """Main application entry point."""
    args = parse_arguments()
    
    # Load configuration
    try:
        with open(args.config, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Error: Configuration file not found: {args.config}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid configuration file: {e}")
        sys.exit(1)
    
    # Setup logging
    if args.debug:
        config['logging']['level'] = 'DEBUG'
    
    logger = setup_logger(args.config)
    
    print_banner()
    
    try:
        # Initialize Excel handler
        excel_handler = ExcelHandler(args.config)
        
        # Override Excel file if specified
        if args.excel:
            excel_handler.excel_file = args.excel
            logger.info(f"Using custom Excel file: {args.excel}")
        
        # Load Excel file
        excel_file = excel_handler.load_excel_file()
        if not excel_file:
            print("Failed to load Excel file. Check the file path and try again.")
            sys.exit(1)
        
        available_sheets = excel_handler.get_available_sheets(excel_file)
        
        # List sheets mode
        if args.list_sheets:
            print("\\nAvailable sheets:")
            for i, sheet_name in enumerate(available_sheets):
                print(f"  {i + 1}: {sheet_name}")
            return
        
        # Determine which sheets to process
        if args.sheets:
            # Parse sheet numbers from command line
            try:
                sheet_indices = [int(i.strip()) - 1 for i in args.sheets.split(',') if i.strip().isdigit()]
                selected_sheets = [available_sheets[i] for i in sheet_indices if 0 <= i < len(available_sheets)]
                
                if not selected_sheets:
                    print("Error: No valid sheet numbers provided")
                    sys.exit(1)
                    
                logger.info(f"Processing sheets from command line: {selected_sheets}")
            except (ValueError, IndexError) as e:
                print(f"Error parsing sheet numbers: {e}")
                sys.exit(1)
        else:
            # Interactive sheet selection
            selected_sheets = excel_handler.get_user_sheet_selection(available_sheets)
            if not selected_sheets:
                print("No sheets selected. Exiting.")
                sys.exit(0)
        
        # Print Chrome setup instructions
        print_chrome_instructions(config)
        input("\\nPress Enter when Chrome is ready and you've navigated to the form page...")
        
        # Initialize browser manager
        with BrowserManager(args.config) as browser:
            if not browser.connect_to_existing_session():
                print("\\nFailed to connect to Chrome. Please ensure:")
                print("1. Chrome is running with remote debugging enabled")
                print("2. You've navigated to the form page")
                print("3. The remote debugging port is correct in config.json")
                sys.exit(1)
            
            logger.info(f"Connected to browser. Current page: {browser.get_page_title()}")
            
            # Initialize form filler
            form_filler = FormFiller(browser, args.config)
            
            # Process each selected sheet
            all_results = []
            
            for sheet_name in selected_sheets:
                print(f"\\nProcessing sheet: {sheet_name}")
                logger.info(f"Loading sheet: {sheet_name}")
                
                # Load and validate sheet
                df = excel_handler.load_and_validate_sheet(excel_file, sheet_name)
                if df is None:
                    logger.error(f"Skipping invalid sheet: {sheet_name}")
                    continue
                
                # Get data summary
                summary = excel_handler.get_sheet_data_summary(df)
                logger.info(f"Sheet summary: {summary['total_rows']} rows, {summary['empty_rows']} empty rows")
                
                # Clean data
                cleaned_df = excel_handler.clean_data_for_processing(df)
                
                # Process the sheet
                result = form_filler.process_sheet_data(sheet_name, cleaned_df)
                all_results.append(result)
                
                # Print progress
                success_rate = (result['successful_rows'] / result['total_rows'] * 100) if result['total_rows'] > 0 else 0
                print(f"Sheet '{sheet_name}': {result['successful_rows']}/{result['total_rows']} rows processed successfully ({success_rate:.1f}%)")
                
                if result['errors']:
                    print(f"  Errors encountered: {len(result['errors'])}")
                    for error in result['errors'][:3]:  # Show first 3 errors
                        print(f"    - {error}")
                    if len(result['errors']) > 3:
                        print(f"    ... and {len(result['errors']) - 3} more errors")
            
            # Print final summary
            if all_results:
                print("\\n" + "=" * 60)
                print("  PROCESSING SUMMARY")
                print("=" * 60)
                
                summary = form_filler.get_processing_summary(all_results)
                
                print(f"Sheets processed: {summary['total_sheets']}")
                print(f"Total rows: {summary['total_rows']}")
                print(f"Successful rows: {summary['successful_rows']}")
                print(f"Failed rows: {summary['failed_rows']}")
                print(f"Success rate: {summary['success_rate']:.1f}%")
                print(f"Total errors: {summary['total_errors']}")
                
                if summary['failed_rows'] > 0:
                    print("\\nCheck the log file for detailed error information.")
                
                print("\\nForm filling completed!")
                logger.info("Form filling process completed")
            
    except KeyboardInterrupt:
        print("\\nOperation cancelled by user.")
        logger.info("Operation cancelled by user")
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"\\nAn unexpected error occurred: {e}")
        print("Check the log file for more details.")
        sys.exit(1)


if __name__ == "__main__":
    main()