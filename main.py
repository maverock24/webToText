import time
import random
import unicodedata
import os
import logging
import sys
import tkinter as tk
from tkinter import scrolledtext, ttk, filedialog, BooleanVar
from threading import Thread
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.common.exceptions import ElementNotInteractableException, StaleElementReferenceException
from selenium.common.exceptions import JavascriptException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Keep existing functions unchanged
def safe_execute_script(driver, script, default_return=None):
    """Execute JavaScript safely with error handling."""
    try:
        return driver.execute_script(script)
    except (JavascriptException, WebDriverException) as e:
        logger.debug(f"JavaScript execution failed: {e}")
        return default_return

def dismiss_dialogs(driver, url, timeout=5):
    """Attempt to dismiss common cookie banners and dialogs with improved error handling."""
    try:
        # Handle specific sites with known patterns
        if "nytimes.com" in url:
            try:
                # Wait longer for NY Times site to fully load
                time.sleep(5)
                
                # Check if any paywall/subscription dialogs exist before attempting to interact
                safe_execute_script(driver, """
                    // Remove subscription modals
                    const modals = document.querySelectorAll('[data-testid="subscription-modal"], [data-testid="complianceBlocker"], [data-testid="onsite-messaging-unit"], .ReactModalPortal');
                    if (modals) {
                        modals.forEach(modal => {
                            if (modal) modal.remove();
                        });
                    }
                    
                    // Make content visible and enable scrolling
                    document.documentElement.style.overflow = 'auto';
                    document.body.style.overflow = 'auto';
                    
                    // Remove any fixed position overlays
                    document.querySelectorAll('[style*="position:fixed"]').forEach(elem => {
                        if (elem) elem.remove();
                    });
                """)
                
                # Try to accept cookies if the button is present
                buttons = driver.find_elements(By.XPATH, "//button[contains(., 'Accept')] | //button[contains(., 'Continue')] | //button[contains(., 'Agree')]")
                for button in buttons:
                    try:
                        if button.is_displayed():
                            safe_execute_script(driver, "arguments[0].click();", button)
                            time.sleep(1)
                    except Exception:
                        pass
                
            except Exception as e:
                logger.warning(f"NY Times specific handling failed: {e}")
        
        # Wait for page to load
        time.sleep(3)
        
        # Common accept button text patterns
        accept_patterns = [
            "accept", "agree", "accept all", "allow", "got it", "i understand", 
            "ok", "continue", "close", "consent", "accept cookies", "reject all"
        ]
        
        # Try switching to iframes that might contain consent forms
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        
        # First try without iframes
        for pattern in accept_patterns:
            try:
                xpath = f"//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{pattern}')] | " \
                       f"//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{pattern}')] | " \
                       f"//div[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{pattern}')]"
                
                elements = driver.find_elements(By.XPATH, xpath)
                for element in elements:
                    try:
                        if element.is_displayed():
                            # Use JavaScript click which is more reliable for overlays
                            safe_execute_script(driver, "arguments[0].click();", element)
                            time.sleep(1)
                    except Exception:
                        continue
            except (ElementNotInteractableException, NoSuchElementException, StaleElementReferenceException):
                continue
        
        # Then try with iframes
        for iframe in iframes:
            try:
                driver.switch_to.frame(iframe)
                for pattern in accept_patterns:
                    try:
                        xpath = f"//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{pattern}')] | " \
                               f"//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{pattern}')]"
                        
                        elements = driver.find_elements(By.XPATH, xpath)
                        for element in elements:
                            try:
                                if element.is_displayed():
                                    safe_execute_script(driver, "arguments[0].click();", element)
                                    time.sleep(1)
                                    break
                            except Exception:
                                continue
                    except Exception:
                        continue
                driver.switch_to.default_content()
            except Exception:
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass
                continue
        
        # Nuclear option: JavaScript to force remove overlays and enable scrolling
        safe_execute_script(driver, """
            try {
                // Remove common overlay elements
                const selectors = [
                    '.modal', '.overlay', '.cookie-banner', '.cookie-dialog', '.cookie-modal', 
                    '.gdpr-modal', '.consent-modal', '.privacy-overlay', '.privacy-popup',
                    '[class*="cookie"]', '[class*="consent"]', '[class*="gdpr"]', '[id*="cookie"]',
                    '[id*="consent"]', '[id*="gdpr"]', '[class*="popup"]', '[class*="modal"]',
                    '[class*="overlay"]'
                ];
                
                selectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(elem => {
                        if (elem) elem.remove();
                    });
                });
                
                // Remove any fixed position elements at the top/bottom of the page
                document.querySelectorAll('div[style*="position:fixed"], div[style*="position: fixed"]').forEach(elem => {
                    if (elem) {
                        const rect = elem.getBoundingClientRect();
                        if ((rect.top <= 10 || window.innerHeight - rect.bottom <= 10) && 
                            (rect.width > window.innerWidth * 0.5)) {
                            elem.remove();
                        }
                    }
                });
                
                // Enable scrolling by removing various no-scroll classes
                const scrollClasses = ['no-scroll', 'modal-open', 'has-overlay', 'overflow-hidden'];
                scrollClasses.forEach(className => {
                    if (document.body.classList) {
                        document.body.classList.remove(className);
                    }
                });
                
                if (document.body.style) document.body.style.overflow = 'auto';
                if (document.body.style) document.body.style.position = 'static';
                if (document.documentElement.style) document.documentElement.style.overflow = 'auto';
            } catch (e) {
                // Silently fail if any JS errors
            }
        """)
        
    except Exception as e:
        logger.error(f"Dialog dismissal attempt failed: {e}")

def fetch_text_from_url(url, callback=None):
    """Fetch and clean ASCII text from a given URL with improved error handling."""
    options = Options()
    options.add_argument("--headless=new")  # Modern headless mode
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=en-US,en;q=0.9")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36")
    options.add_argument("--start-maximized")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    # Apply stealth mode
    stealth(driver,
        languages=["en-US", "en"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )
    
    try:
        logger.info(f"Fetching content from {url}")
        if callback:
            callback(f"Fetching content from {url}...")
        
        driver.get(url)
        time.sleep(random.uniform(5, 7))  # Let JavaScript load content
        
        # Dismiss cookie banners and other dialogs
        if callback:
            callback(f"Dismissing dialogs on {url}...")
        dismiss_dialogs(driver, url)
        
        # Allow a bit more time for everything to settle after dismissing dialogs
        time.sleep(2)
        
        # Scroll down gradually to load lazy content, with error handling
        try:
            if callback:
                callback(f"Scrolling page to load content...")
                
            height = safe_execute_script(driver, "return document.body.scrollHeight", 1000)
            if height:
                for i in range(1, 5):
                    safe_execute_script(driver, f"window.scrollTo(0, {height * i / 5});")
                    time.sleep(0.5)
                safe_execute_script(driver, "window.scrollTo(0, 0);")  # Back to top
        except Exception as e:
            logger.warning(f"Scrolling failed: {e}")
        
        # Try to get just the main content if possible
        if callback:
            callback(f"Extracting main content...")
            
        main_content = None
        selectors = [
            # Main content selectors in order of priority
            'article', 'main', '.article-content', '.article-body', '.story-body',
            '.content', '#content', '.main-content', '.post-content',
            # News-specific selectors
            '.article__body', '.entry-content', '.story', '.article__content',
            # Generic content containers as fallback
            '.container', '.page-content', '.page'
        ]
        
        for selector in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    try:
                        if element.is_displayed() and element.text and len(element.text.strip()) > 200:
                            main_content = element.text
                            break
                    except Exception:
                        continue
                if main_content:
                    break
            except Exception:
                continue
        
        # Fall back to body if no main content found or if it's too short
        if not main_content or len(main_content.strip()) < 200:
            try:
                main_content = driver.find_element(By.TAG_NAME, "body").text
            except Exception as e:
                logger.error(f"Failed to get body text: {e}")
                return f"Error extracting text from {url}: {e}"
        
        # Clean the text
        if main_content:
            if callback:
                callback(f"Cleaning and processing text...")
                
            ascii_text = unicodedata.normalize('NFKD', main_content).encode('ascii', 'ignore').decode('ascii')
            
            # Additional cleaning to remove common noise
            lines = ascii_text.split('\n')
            filtered_lines = []
            
            for line in lines:
                line = line.strip()
                # Skip very short lines, navigational elements, etc.
                if (len(line) > 3 and 
                    not line.startswith('Search') and 
                    not line.lower().startswith('sign in') and
                    not line.lower().startswith('log in') and
                    not line.lower().startswith('subscribe') and
                    not 'cookie' in line.lower()):
                    filtered_lines.append(line)
            
            return '\n'.join(filtered_lines)
        else:
            return f"No content could be extracted from {url}"
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        return f"Error fetching {url}: {e}"
    finally:
        try:
            driver.quit()
        except Exception:
            pass

def save_text_to_file(url, text, output_dir="extracted_texts"):
    """Save extracted text to a file."""
    try:
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Create a valid filename from the URL
        from urllib.parse import urlparse
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.replace("www.", "")
        filename = f"{domain.replace('.', '_')}.txt"
        filepath = os.path.join(output_dir, filename)
        
        # Save the text
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(text)
        
        return filepath
    except Exception as e:
        logger.error(f"Error saving text to file: {e}")
        return None

# Fixed WebToTextGUI class - removing duplicates and drag-and-drop functionality
class WebToTextGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Web To Text - URL Scraper")
        self.root.geometry("800x700")
        
        # Configure styles
        style = ttk.Style()
        style.configure("TButton", padding=6, relief="flat", background="#ccc")
        style.configure("TFrame", background="#f0f0f0")
        style.configure("TLabel", background="#f0f0f0", font=('Arial', 10))
        
        # Main frame
        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # URL input section
        ttk.Label(main_frame, text="Enter URLs (one per line):").pack(anchor=tk.W, pady=(0, 5))
        
        self.url_input = scrolledtext.ScrolledText(main_frame, height=10)
        self.url_input.pack(fill=tk.BOTH, expand=False, pady=(0, 10))
        
        # Add paste button for convenience
        paste_button = ttk.Button(main_frame, text="Paste URL", command=self.paste_url)
        paste_button.pack(anchor=tk.W, pady=(0, 10))
        
        # Control panel frame
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=10)
        
        # Save to file checkbox
        self.save_to_file = BooleanVar()
        self.save_to_file.set(True)
        save_check = ttk.Checkbutton(control_frame, text="Save to files", variable=self.save_to_file)
        save_check.pack(side=tk.LEFT, padx=(0, 10))
        
        # Output directory button
        self.output_dir = tk.StringVar(value="extracted_texts")
        ttk.Button(control_frame, text="Output Directory", command=self.select_output_dir).pack(side=tk.LEFT, padx=(0, 10))
        
        # Scrape button
        self.scrape_btn = ttk.Button(control_frame, text="Scrape URLs", command=self.start_scraping)
        self.scrape_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # Clear button
        ttk.Button(control_frame, text="Clear All", command=self.clear_all).pack(side=tk.LEFT)
        
        # Status label
        self.status_var = tk.StringVar(value="Ready")
        status_label = ttk.Label(main_frame, textvariable=self.status_var)
        status_label.pack(fill=tk.X, pady=(5, 10))
        
        # Results section
        ttk.Label(main_frame, text="Results:").pack(anchor=tk.W, pady=(0, 5))
        
        self.results_text = scrolledtext.ScrolledText(main_frame, height=20)
        self.results_text.pack(fill=tk.BOTH, expand=True)
        self.results_text.config(state=tk.DISABLED)
        
        # Add keyboard shortcut for pasting (Ctrl+V)
        self.root.bind("<Control-v>", lambda e: self.paste_url())
    
    def paste_url(self):
        """Paste URL from clipboard"""
        try:
            clipboard = self.root.clipboard_get()
            if clipboard.strip().startswith('http'):
                current_text = self.url_input.get(1.0, tk.END)
                if current_text.strip():
                    # If there's already text, add a newline first
                    self.url_input.insert(tk.END, "\n" + clipboard)
                else:
                    self.url_input.insert(tk.END, clipboard)
                self.status_var.set("URL pasted from clipboard")
            else:
                self.status_var.set("Clipboard content is not a URL")
        except Exception as e:
            self.status_var.set(f"Failed to paste: {e}")
    
    def select_output_dir(self):
        directory = filedialog.askdirectory(initialdir=self.output_dir.get())
        if directory:
            self.output_dir.set(directory)
            self.status_var.set(f"Output directory: {directory}")
    
    def clear_all(self):
        self.url_input.delete(1.0, tk.END)
        self.results_text.config(state=tk.NORMAL)
        self.results_text.delete(1.0, tk.END)
        self.results_text.config(state=tk.DISABLED)
        self.status_var.set("Ready")
    
    def update_results(self, text):
        self.results_text.config(state=tk.NORMAL)
        self.results_text.insert(tk.END, text + "\n")
        self.results_text.see(tk.END)  # Auto-scroll to the latest output
        self.results_text.config(state=tk.DISABLED)
        self.root.update_idletasks()  # Force GUI update
    
    def update_status(self, status):
        self.status_var.set(status)
        self.root.update_idletasks()
    
    def start_scraping(self):
        # Disable the scrape button
        self.scrape_btn.config(state=tk.DISABLED)
        
        # Get URLs from input field
        url_text = self.url_input.get(1.0, tk.END).strip()
        urls = [url.strip() for url in url_text.split('\n') if url.strip().startswith('http')]
        
        if not urls:
            self.update_status("No valid URLs found. Please enter URLs starting with http:// or https://")
            self.scrape_btn.config(state=tk.NORMAL)
            return
        
        # Clear previous results
        self.results_text.config(state=tk.NORMAL)
        self.results_text.delete(1.0, tk.END)
        self.results_text.config(state=tk.DISABLED)
        
        # Start a worker thread to handle the scraping
        worker_thread = Thread(target=self.scrape_worker, args=(urls,))
        worker_thread.daemon = True
        worker_thread.start()
    
    def scrape_worker(self, urls):
        try:
            self.update_status(f"Processing {len(urls)} URLs...")
            
            for url in urls:
                self.update_results(f"\n=== Content from {url} ===\n")
                
                # Fetch text content
                text = fetch_text_from_url(url, callback=self.update_status)
                self.update_results(text)
                
                # Save to file if requested
                if self.save_to_file.get():
                    filepath = save_text_to_file(url, text, self.output_dir.get())
                    if filepath:
                        self.update_results(f"\nText saved to: {filepath}")
                
                self.update_results("\n" + "-" * 80 + "\n")
                
                # Random delay to reduce chances of being blocked
                delay = random.uniform(1, 3)  # Shorter delay for GUI application
                self.update_status(f"Waiting {delay:.1f} seconds before next URL...")
                time.sleep(delay)
            
            self.update_status("Scraping completed!")
        except Exception as e:
            logger.error(f"Error in scrape worker: {e}")
            self.update_status(f"Error: {e}")
        finally:
            # Re-enable the scrape button
            self.scrape_btn.config(state=tk.NORMAL)

def main():
    """Main function that starts the GUI or falls back to CLI if --no-gui is provided."""
    if "--no-gui" in sys.argv:
        # Command-line interface version
        urls = []
        
        print("Enter URLs (type 'done' when finished):")
        while True:
            url = input("URL: ").strip()
            if url.lower() == 'done':
                break
            urls.append(url)
        
        if not urls:
            print("No URLs provided. Exiting.")
            return
        
        save_to_file = input("Save extracted text to files? (y/n): ").strip().lower() == 'y'
        output_dir = "extracted_texts"
        
        print("\nExtracted ASCII text from pages:")
        for url in urls:
            print(f"\n=== Content from {url} ===\n")
            text = fetch_text_from_url(url)
            print(text)
            
            if save_to_file:
                filepath = save_text_to_file(url, text, output_dir)
                if filepath:
                    print(f"\nText saved to: {filepath}")
            
            print("\n" + "-" * 80 + "\n")
            
            # Random delay to reduce chances of being blocked
            time.sleep(random.uniform(5, 10))
    else:
        # GUI version
        try:
            root = tk.Tk()
            app = WebToTextGUI(root)
            root.mainloop()
        except Exception as e:
            logger.error(f"Failed to start GUI: {e}")
            print(f"Error starting GUI: {e}")
            print("Falling back to command line mode. Use '--no-gui' flag to run in command line mode.")
            print("Example: python main.py --no-gui")
            # Don't call main() again to avoid infinite recursion
            sys.exit(1)

if __name__ == "__main__":
    main()