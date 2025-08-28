# Opiskelusuunnitelmoittaja - Study Plan Form Filler

Automated form filling tool for study plans using Chrome WebDriver. This tool reads data from Excel files and automatically fills web forms, with robust error handling and retry logic.

## Features

- **Chrome WebDriver Integration**: Uses Chrome browser with remote debugging
- **Excel Data Processing**: Reads multiple sheets from Excel files (.xlsx)
- **Robust Error Handling**: Retry logic with exponential backoff
- **Modular Architecture**: Clean separation of concerns with dedicated classes
- **Comprehensive Logging**: Detailed logging with configurable levels
- **Command Line Interface**: Interactive and automated modes
- **Data Validation**: Validates Excel data before processing
- **Progress Tracking**: Real-time progress updates and summary reports

## Installation

1. **Clone or download the project**
2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Ensure Chrome browser is installed**

## Setup

### Chrome Browser Configuration

The application requires Chrome to run with remote debugging enabled:

1. **Close all Chrome windows**
2. **Open Command Prompt as Administrator**
3. **Run the Chrome launch command**:
   ```cmd
   "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\\Temp\\ChromeProfile"
   ```
4. **Navigate to your form page in the opened Chrome window**

### Excel File Preparation

Ensure your Excel file (`Opintosuunnitelmat.xlsx`) contains sheets with the following columns:
- `Osaamistavoite` - Learning objective
- `Laajuus` - Scope/Credits  
- `Suoritustapa / osaaminen hankitaan` - Method of completion
- `Suoritusajankohta` - Completion time

## Usage

### Basic Usage (Interactive Mode)
```bash
python main.py
```

### Command Line Options
```bash
# List available sheets
python main.py --list-sheets

# Process specific sheets (by number)
python main.py --sheets 1,3,5

# Use custom Excel file
python main.py --excel "path/to/your/file.xlsx"

# Use custom configuration
python main.py --config "custom_config.json"

# Enable debug logging
python main.py --debug
```

### Complete Example
```bash
# Install dependencies
pip install -r requirements.txt

# Start Chrome with remote debugging (as Administrator)
"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\\Temp\\ChromeProfile"

# Navigate to your form page in Chrome

# Run the application
python main.py --sheets 1,2 --debug
```

## Configuration

The application uses `config.json` for configuration. Key settings include:

### Browser Settings
```json
{
  "browser": {
    "type": "chrome",
    "remote_debugging_port": 9222,
    "user_data_dir": "C:\\\\Temp\\\\ChromeProfile",
    "wait_timeout": 10,
    "page_load_timeout": 30
  }
}
```

### Selectors and Form Fields
```json
{
  "selectors": {
    "table_tbody": "/html/body/div[2]/div/div/div[2]/div/main/form/div[1]/div/div[2]/div/div/table/tbody",
    "add_row_button": "//*[@id=\\"f-prepeater9700__add\\"]",
    "form_fields": {
      "osaamistavoite": "td[1]",
      "laajuus": "td[2]",
      "suoritustapa": "td[3]",
      "suoritusajankohta": "td[4]"
    }
  }
}
```

### Retry Configuration
```json
{
  "retry": {
    "max_attempts": 3,
    "delay_between_attempts": 2,
    "backoff_multiplier": 2
  }
}
```

## Project Structure

```
Opiskelusuunnitelmoittaja/
├── main.py                    # Main entry point
├── config.json               # Configuration file
├── requirements.txt          # Python dependencies
├── README.md                 # This file
├── Opintosuunnitelmat.xlsx   # Excel data file
├── src/                      # Source code modules
│   ├── __init__.py
│   ├── browser_manager.py    # Browser WebDriver management
│   ├── excel_handler.py      # Excel file operations
│   ├── form_filler.py        # Web form filling logic
│   └── utils/
│       ├── __init__.py
│       └── logger.py         # Logging configuration
└── logs/
    └── app.log               # Application log file
```

## Error Handling

The application includes comprehensive error handling:

- **Retry Logic**: Failed operations are retried with exponential backoff
- **Graceful Degradation**: Single row failures don't stop the entire process
- **Detailed Logging**: All errors are logged with context and timestamps
- **User-Friendly Messages**: Clear error messages and progress updates

## Logging

Logs are written to both console and file (`logs/app.log`). Log levels:
- **INFO**: General progress and status updates
- **WARNING**: Non-critical issues that don't stop execution
- **ERROR**: Critical errors that may affect processing
- **DEBUG**: Detailed technical information (use `--debug` flag)

## Troubleshooting

### Common Issues

1. **"Failed to connect to Chrome session"**
   - Ensure Chrome is running with remote debugging enabled
   - Check that the port (9222) is not in use by another application
   - Verify the Chrome launch command in config.json

2. **"Excel file not found"**
   - Check the file path in config.json
   - Ensure the Excel file exists and is not open in another application

3. **"Missing required columns"**
   - Verify your Excel sheets have the required column names
   - Check the column mapping in config.json

4. **Form fields not found**
   - The web form structure may have changed
   - Update the XPath selectors in config.json
   - Use browser developer tools to find correct selectors

### Debug Mode

Use debug mode for detailed troubleshooting:
```bash
python main.py --debug
```

This will show:
- Detailed WebDriver operations
- Element selection attempts
- Data processing steps
- Network timeouts and retries

## Requirements

- **Python 3.7+**
- **Google Chrome browser**
- **Python packages**: selenium, webdriver-manager, pandas, openpyxl
- **Administrative privileges** (for Chrome launch command)

## Support

- Check the log file (`logs/app.log`) for detailed error information
- Ensure all requirements are installed correctly
- Verify Chrome browser setup and remote debugging configuration
- Test with a small Excel file first to validate the setup