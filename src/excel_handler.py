import pandas as pd
import json
import logging
import os
from typing import List, Dict, Any, Optional, Tuple


class ExcelHandler:
    """Handles Excel file operations and data validation."""
    
    def __init__(self, config_path: str = "config.json"):
        """
        Initialize ExcelHandler with configuration.
        
        Args:
            config_path: Path to configuration file
        """
        self.logger = logging.getLogger('suunnitelmoittaja.excel')
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        self.excel_file = self.config.get('files', {}).get('excel_file', 'Opintosuunnitelmat.xlsx')
        self.column_mapping = self.config.get('excel_columns', {})
        
    def load_excel_file(self) -> Optional[pd.ExcelFile]:
        """
        Load Excel file and validate its existence.
        
        Returns:
            pd.ExcelFile object if successful, None otherwise
        """
        try:
            if not os.path.exists(self.excel_file):
                self.logger.error(f"Excel file not found: {self.excel_file}")
                return None
                
            excel_file = pd.ExcelFile(self.excel_file)
            self.logger.info(f"Excel file loaded successfully: {self.excel_file}")
            self.logger.info(f"Available sheets: {excel_file.sheet_names}")
            
            return excel_file
            
        except Exception as e:
            self.logger.error(f"Failed to load Excel file: {e}")
            return None
    
    def get_available_sheets(self, excel_file: pd.ExcelFile) -> List[str]:
        """
        Get list of available sheet names.
        
        Args:
            excel_file: Loaded Excel file object
            
        Returns:
            List of sheet names
        """
        return excel_file.sheet_names if excel_file else []
    
    def validate_sheet_columns(self, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        Validate that required columns exist in the dataframe.
        
        Args:
            df: DataFrame to validate
            
        Returns:
            Tuple of (is_valid, list_of_missing_columns)
        """
        required_columns = list(self.column_mapping.values())
        missing_columns = []
        
        for column in required_columns:
            if column not in df.columns:
                missing_columns.append(column)
        
        is_valid = len(missing_columns) == 0
        
        if not is_valid:
            self.logger.warning(f"Missing required columns: {missing_columns}")
            self.logger.info(f"Available columns: {list(df.columns)}")
        
        return is_valid, missing_columns
    
    def load_and_validate_sheet(self, excel_file: pd.ExcelFile, sheet_name: str) -> Optional[pd.DataFrame]:
        """
        Load specific sheet and validate its structure.
        
        Args:
            excel_file: Loaded Excel file object
            sheet_name: Name of sheet to load
            
        Returns:
            DataFrame if valid, None otherwise
        """
        try:
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
            self.logger.info(f"Sheet '{sheet_name}' loaded with {len(df)} rows")
            
            # Validate columns
            is_valid, missing_columns = self.validate_sheet_columns(df)
            if not is_valid:
                self.logger.error(f"Sheet '{sheet_name}' has missing columns: {missing_columns}")
                return None
            
            # Log data summary
            self.logger.info(f"Sheet '{sheet_name}' validation passed")
            self.logger.debug(f"Columns: {list(df.columns)}")
            
            return df
            
        except Exception as e:
            self.logger.error(f"Failed to load sheet '{sheet_name}': {e}")
            return None
    
    def get_sheet_data_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Get summary statistics for the sheet data.
        
        Args:
            df: DataFrame to analyze
            
        Returns:
            Dictionary with summary information
        """
        summary = {
            'total_rows': len(df),
            'empty_rows': 0,
            'column_stats': {}
        }
        
        # Count empty rows (all NaN values)
        summary['empty_rows'] = df.isnull().all(axis=1).sum()
        
        # Column statistics
        for col_key, col_name in self.column_mapping.items():
            if col_name in df.columns:
                series = df[col_name]
                summary['column_stats'][col_key] = {
                    'total_values': len(series),
                    'non_empty_values': series.notna().sum(),
                    'empty_values': series.isna().sum(),
                    'unique_values': series.nunique()
                }
        
        return summary
    
    def clean_data_for_processing(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean and prepare data for form filling.
        
        Args:
            df: Raw DataFrame
            
        Returns:
            Cleaned DataFrame
        """
        cleaned_df = df.copy()
        
        # Convert all values to strings and handle NaN
        for col_key, col_name in self.column_mapping.items():
            if col_name in cleaned_df.columns:
                cleaned_df[col_name] = cleaned_df[col_name].astype(str)
                cleaned_df[col_name] = cleaned_df[col_name].replace('nan', '')
                cleaned_df[col_name] = cleaned_df[col_name].fillna('')
        
        # Remove completely empty rows
        cleaned_df = cleaned_df.dropna(how='all')
        
        self.logger.info(f"Data cleaned: {len(df)} -> {len(cleaned_df)} rows")
        
        return cleaned_df
    
    def get_user_sheet_selection(self, available_sheets: List[str]) -> List[str]:
        """
        Get user selection of sheets to process.
        
        Args:
            available_sheets: List of available sheet names
            
        Returns:
            List of selected sheet names
        """
        print("\\nSaatavilla olevat sheetit:")
        for idx, sheet_name in enumerate(available_sheets):
            print(f"{idx + 1}: {sheet_name}")
        
        while True:
            try:
                sheet_input = input("\\nSyötä niiden sheetien numerot, jotka haluat täyttää (pilkuilla erotettuna): ")
                indices = [int(i.strip()) - 1 for i in sheet_input.split(',') if i.strip().isdigit()]
                
                # Validate indices
                valid_indices = [i for i in indices if 0 <= i < len(available_sheets)]
                
                if not valid_indices:
                    print("Virheelliset sheet-numerot. Yritä uudelleen.")
                    continue
                
                selected_sheets = [available_sheets[i] for i in valid_indices]
                self.logger.info(f"User selected sheets: {selected_sheets}")
                
                return selected_sheets
                
            except ValueError:
                print("Virheellinen syöte. Syötä numerot pilkuilla erotettuna.")
            except KeyboardInterrupt:
                self.logger.info("User cancelled sheet selection")
                return []