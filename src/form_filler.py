from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
import pandas as pd
import json
import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from .browser_manager import BrowserManager


class FormFiller:
    """Handles web form filling operations with retry logic and error handling."""
    
    def __init__(self, browser_manager: BrowserManager, config_path: str = "config.json"):
        """
        Initialize FormFiller with browser manager and configuration.
        
        Args:
            browser_manager: BrowserManager instance
            config_path: Path to configuration file
        """
        self.logger = logging.getLogger('suunnitelmoittaja.form_filler')
        self.browser = browser_manager
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        self.selectors = self.config.get('selectors', {})
        self.column_mapping = self.config.get('excel_columns', {})
        self.retry_config = self.config.get('retry', {})
        
        self.current_row = 1  # Track current table row
        
    def add_table_row(self) -> bool:
        """
        Add a new row to the form table with retry logic.
        
        Returns:
            True if row added successfully, False otherwise
        """
        max_attempts = self.retry_config.get('max_attempts', 3)
        delay = self.retry_config.get('delay_between_attempts', 2)
        
        for attempt in range(max_attempts):
            try:
                add_button_xpath = self.selectors.get('add_row_button')
                if not add_button_xpath:
                    self.logger.error("Add row button selector not configured")
                    return False
                
                # Wait for button to be clickable
                add_button = self.browser.wait_for_element(By.XPATH, add_button_xpath)
                if not add_button:
                    raise Exception("Add row button not found")
                
                # Scroll to button and click
                self.browser.scroll_to_element(add_button)
                
                # Use ActionChains for more reliable clicking
                ActionChains(self.browser.driver).move_to_element(add_button).click().perform()
                
                # Wait a moment for the row to be created
                time.sleep(1)
                
                self.logger.debug(f"Successfully added table row (attempt {attempt + 1})")
                return True
                
            except Exception as e:
                self.logger.warning(f"Failed to add row (attempt {attempt + 1}/{max_attempts}): {e}")
                if attempt < max_attempts - 1:
                    time.sleep(delay)
                    delay *= self.retry_config.get('backoff_multiplier', 2)
        
        self.logger.error("Failed to add table row after all attempts")
        return False
    
    def find_form_field(self, row_index: int, field_type: str) -> Optional[Any]:
        """
        Find a specific form field in the table.
        
        Args:
            row_index: Table row index (1-based)
            field_type: Type of field (osaamistavoite, laajuus, etc.)
            
        Returns:
            WebElement if found, None otherwise
        """
        try:
            table_xpath = self.selectors.get('table_tbody')
            field_selector = self.selectors.get('form_fields', {}).get(field_type)
            
            if not table_xpath or not field_selector:
                self.logger.error(f"Selector not configured for field: {field_type}")
                return None
            
            # Construct full xpath for the field
            row_xpath = f"{table_xpath}/tr[{row_index}]"
            field_xpath = f"{row_xpath}/{field_selector}"
            
            # Find the cell containing the input field
            field_cell = self.browser.driver.find_element(By.XPATH, field_xpath)
            
            # Find the input element within the cell
            input_element = field_cell.find_element(By.TAG_NAME, 'input')
            
            return input_element
            
        except Exception as e:
            self.logger.debug(f"Field not found: {field_type} at row {row_index}: {e}")
            return None
    
    def fill_form_field(self, field_element, value: str, field_name: str) -> bool:
        """
        Fill a single form field with retry logic.
        
        Args:
            field_element: WebElement to fill
            value: Value to enter
            field_name: Name of field for logging
            
        Returns:
            True if filled successfully, False otherwise
        """
        max_attempts = self.retry_config.get('max_attempts', 3)
        delay = 0.5  # Short delay for field operations
        
        for attempt in range(max_attempts):
            try:
                # Clear the field first
                field_element.clear()
                
                # Enter the value (use space if empty to avoid validation issues)
                field_value = value.strip() if value.strip() else ' '
                field_element.send_keys(field_value)
                
                # Verify the value was entered
                actual_value = field_element.get_attribute('value')
                if actual_value == field_value:
                    self.logger.debug(f"Field '{field_name}' filled successfully: '{field_value}'")
                    return True
                
                self.logger.warning(f"Field value mismatch for '{field_name}': expected '{field_value}', got '{actual_value}'")
                
            except Exception as e:
                self.logger.warning(f"Failed to fill field '{field_name}' (attempt {attempt + 1}/{max_attempts}): {e}")
                
            if attempt < max_attempts - 1:
                time.sleep(delay)
        
        self.logger.error(f"Failed to fill field '{field_name}' after all attempts")
        return False
    
    def fill_table_row(self, row_index: int, row_data: pd.Series) -> Tuple[bool, Dict[str, bool]]:
        """
        Fill a complete table row with data from Excel.
        
        Args:
            row_index: Table row index (1-based)
            row_data: Pandas Series containing row data
            
        Returns:
            Tuple of (overall_success, field_results_dict)
        """
        field_results = {}
        overall_success = True
        
        # Map of field types to Excel column names
        field_mapping = {
            'osaamistavoite': self.column_mapping.get('osaamistavoite'),
            'laajuus': self.column_mapping.get('laajuus'),
            'suoritustapa': self.column_mapping.get('suoritustapa'),
            'suoritusajankohta': self.column_mapping.get('suoritusajankohta')
        }
        
        for field_type, column_name in field_mapping.items():
            if not column_name:
                self.logger.warning(f"Column mapping not found for field: {field_type}")
                field_results[field_type] = False
                overall_success = False
                continue
            
            # Get field element
            field_element = self.find_form_field(row_index, field_type)
            if not field_element:
                self.logger.error(f"Field element not found: {field_type} at row {row_index}")
                field_results[field_type] = False
                overall_success = False
                continue
            
            # Get value from Excel data
            field_value = str(row_data.get(column_name, '')) if pd.notna(row_data.get(column_name)) else ''
            
            # Fill the field
            success = self.fill_form_field(field_element, field_value, f"{field_type}[{row_index}]")
            field_results[field_type] = success
            
            if not success:
                overall_success = False
        
        return overall_success, field_results
    
    def process_sheet_data(self, sheet_name: str, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Process complete sheet data and fill form.
        
        Args:
            sheet_name: Name of Excel sheet being processed
            df: DataFrame containing sheet data
            
        Returns:
            Dictionary with processing results
        """
        self.logger.info(f"Starting to process sheet: {sheet_name}")
        
        results = {
            'sheet_name': sheet_name,
            'total_rows': len(df),
            'processed_rows': 0,
            'successful_rows': 0,
            'failed_rows': 0,
            'errors': []
        }
        
        # First, ensure we have enough rows in the form table
        required_rows = len(df)
        self.logger.info(f"Ensuring table has {required_rows} rows for sheet: {sheet_name}")
        
        # Add required rows
        for i in range(required_rows):
            if not self.add_table_row():
                error_msg = f"Failed to add row {i + 1} for sheet {sheet_name}"
                self.logger.error(error_msg)
                results['errors'].append(error_msg)
                return results
        
        # Process each data row
        for index, row_data in df.iterrows():
            try:
                self.logger.info(f"Processing sheet '{sheet_name}', data row {index + 1}/{len(df)}")
                
                # Fill the current table row
                success, field_results = self.fill_table_row(self.current_row, row_data)
                
                results['processed_rows'] += 1
                
                if success:
                    results['successful_rows'] += 1
                    self.logger.info(f"Successfully filled row {self.current_row} with data from '{sheet_name}' row {index + 1}")
                else:
                    results['failed_rows'] += 1
                    error_msg = f"Failed to completely fill row {self.current_row} from sheet '{sheet_name}' row {index + 1}"
                    self.logger.warning(error_msg)
                    results['errors'].append(error_msg)
                
                self.current_row += 1
                
            except Exception as e:
                error_msg = f"Unexpected error processing sheet '{sheet_name}' row {index + 1}: {e}"
                self.logger.error(error_msg)
                results['errors'].append(error_msg)
                results['failed_rows'] += 1
                self.current_row += 1  # Move to next row even on error
        
        # Add separator row between sheets
        if self.add_table_row():
            self.logger.info(f"Added separator row after sheet: {sheet_name}")
            self.current_row += 1
        
        self.logger.info(f"Completed processing sheet '{sheet_name}': {results['successful_rows']}/{results['total_rows']} rows successful")
        
        return results
    
    def get_processing_summary(self, all_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate summary of all processing results.
        
        Args:
            all_results: List of results from each sheet
            
        Returns:
            Summary dictionary
        """
        summary = {
            'total_sheets': len(all_results),
            'total_rows': sum(r['total_rows'] for r in all_results),
            'successful_rows': sum(r['successful_rows'] for r in all_results),
            'failed_rows': sum(r['failed_rows'] for r in all_results),
            'total_errors': sum(len(r['errors']) for r in all_results),
            'sheet_details': all_results
        }
        
        summary['success_rate'] = (summary['successful_rows'] / summary['total_rows'] * 100) if summary['total_rows'] > 0 else 0
        
        return summary