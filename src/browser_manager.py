from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
import json
import logging
import time
from typing import Optional, Dict, Any


class BrowserManager:
    """Manages browser operations and WebDriver lifecycle."""
    
    def __init__(self, config_path: str = "config.json"):
        """
        Initialize BrowserManager with configuration.
        
        Args:
            config_path: Path to configuration file
        """
        self.logger = logging.getLogger('suunnitelmoittaja.browser')
        self.driver: Optional[webdriver.Chrome] = None
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        self.browser_config = self.config.get('browser', {})
        
    def connect_to_existing_session(self) -> bool:
        """
        Connect to existing Chrome session with remote debugging enabled.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            chrome_options = ChromeOptions()
            chrome_options.add_experimental_option(
                "debuggerAddress", 
                f"127.0.0.1:{self.browser_config.get('remote_debugging_port', 9222)}"
            )
            
            # Additional Chrome options for stability
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-extensions")
            
            service = ChromeService(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Set timeouts
            self.driver.implicitly_wait(self.browser_config.get('wait_timeout', 10))
            self.driver.set_page_load_timeout(self.browser_config.get('page_load_timeout', 30))
            
            self.logger.info("Successfully connected to existing Chrome session")
            self.logger.info(f"Current page title: {self.driver.title}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to connect to Chrome session: {e}")
            self.logger.info("Make sure Chrome is running with remote debugging enabled:")
            self.logger.info(f"Command: {self.browser_config.get('launch_command', 'Chrome launch command not configured')}")
            return False
    
    def wait_for_element(self, by: By, value: str, timeout: Optional[int] = None) -> Optional[Any]:
        """
        Wait for element to be clickable.
        
        Args:
            by: Selenium By locator type
            value: Locator value
            timeout: Custom timeout (uses config default if not provided)
            
        Returns:
            WebElement if found, None if timeout
        """
        if not self.driver:
            self.logger.error("No active WebDriver session")
            return None
            
        try:
            wait_time = timeout or self.browser_config.get('wait_timeout', 10)
            element = WebDriverWait(self.driver, wait_time).until(
                EC.element_to_be_clickable((by, value))
            )
            return element
        except Exception as e:
            self.logger.warning(f"Element not found: {by}={value}, error: {e}")
            return None
    
    def scroll_to_element(self, element) -> None:
        """
        Scroll element into view.
        
        Args:
            element: WebElement to scroll to
        """
        if self.driver and element:
            try:
                self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                time.sleep(0.5)  # Small delay for scroll to complete
            except Exception as e:
                self.logger.warning(f"Failed to scroll to element: {e}")
    
    def get_current_url(self) -> Optional[str]:
        """
        Get current page URL.
        
        Returns:
            Current URL or None if no active session
        """
        if self.driver:
            return self.driver.current_url
        return None
    
    def get_page_title(self) -> Optional[str]:
        """
        Get current page title.
        
        Returns:
            Page title or None if no active session
        """
        if self.driver:
            return self.driver.title
        return None
    
    def quit(self) -> None:
        """Close the browser session."""
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("Browser session closed successfully")
            except Exception as e:
                self.logger.error(f"Error closing browser: {e}")
            finally:
                self.driver = None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.quit()