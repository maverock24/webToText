#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WebToText - A tool to extract text from web pages using Chrome Remote Debugging
"""

import subprocess
import os
import sys
import platform
import time
import json
import re
import logging
import threading
import random
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
from urllib.parse import urlparse
import websocket
import requests
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ChromeRemoteDebugger:
    """Class to interface with Chrome via the DevTools Protocol"""
    
    def __init__(self, host='localhost', port=9222):
        """Initialize connection to Chrome"""
        self.host = host
        self.port = port
        self.ws = None
        self.tab_id = None
        self.request_id = 0
        
    def connect(self):
        """Connect to an existing Chrome instance with debugging enabled"""
        try:
            # Get available tabs
            response = requests.get(f"http://{self.host}:{self.port}/json")
            if response.status_code != 200:
                return False, f"Failed to connect: {response.status_code}"
            
            tabs = response.json()
            if not tabs:
                return False, "No Chrome tabs found. Is Chrome running with --remote-debugging-port?"
            
            # Find a suitable tab or create a new one
            for tab in tabs:
                if 'webSocketDebuggerUrl' in tab and tab['type'] == 'page':
                    self.tab_id = tab['id']
                    ws_url = tab['webSocketDebuggerUrl']
                    self.ws = websocket.create_connection(ws_url)
                    return True, "Connected successfully"
                    
            # If no suitable tab found, create a new one
            response = requests.get(f"http://{self.host}:{self.port}/json/new")
            if response.status_code != 200:
                return False, "Failed to create new tab"
                
            tab = response.json()
            self.tab_id = tab['id']
            ws_url = tab['webSocketDebuggerUrl']
            self.ws = websocket.create_connection(ws_url)
            return True, "Connected to new tab"
            
        except Exception as e:
            return False, f"Connection error: {str(e)}"
    
    def navigate(self, url):
        """Navigate to a URL"""
        if not self.ws:
            return False, "Not connected to Chrome"
        
        try:
            self.request_id += 1
            self.ws.send(json.dumps({
                "id": self.request_id,
                "method": "Page.navigate",
                "params": {"url": url}
            }))
            
            # Wait for navigation to complete
            while True:
                result = json.loads(self.ws.recv())
                if 'id' in result and result['id'] == self.request_id:
                    return True, "Navigation successful"
                if 'method' in result and result['method'] == 'Page.loadEventFired':
                    return True, "Page loaded"
                    
        except Exception as e:
            return False, f"Navigation error: {str(e)}"
    
    def get_document(self):
        """Get the document object"""
        if not self.ws:
            return None
            
        try:
            # First get the document
            self.request_id += 1
            self.ws.send(json.dumps({
                "id": self.request_id,
                "method": "DOM.getDocument"
            }))
            
            result = json.loads(self.ws.recv())
            if 'result' in result and 'root' in result['result']:
                return result['result']['root']
            return None
        except Exception as e:
            logger.error(f"Error getting document: {e}")
            return None
    
    def execute_script(self, script):
        """Execute JavaScript in the page"""
        if not self.ws:
            return None
            
        try:
            self.request_id += 1
            self.ws.send(json.dumps({
                "id": self.request_id,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": script,
                    "returnByValue": True
                }
            }))
            
            result = json.loads(self.ws.recv())
            if ('result' in result and 'result' in result['result'] and 
                'value' in result['result']['result']):
                return result['result']['result']['value']
            return None
        except Exception as e:
            logger.error(f"Error executing script: {e}")
            return None
    
    def extract_text_from_all_tabs(self):
        """Extract text from all open tabs in Chrome"""
        results = []
        tabs = self.get_all_tabs()
        
        # Store current tab if we're connected
        current_tab_id = self.tab_id
        
        for tab in tabs:
            try:
                # Connect to this tab
                if 'webSocketDebuggerUrl' not in tab:
                    continue
                    
                # Close existing connection if any
                if self.ws:
                    self.ws.close()
                    
                # Connect to the new tab
                self.tab_id = tab['id']
                self.ws = websocket.create_connection(tab['webSocketDebuggerUrl'])
                
                # Get tab URL and title
                url = tab.get('url', 'Unknown URL')
                title = tab.get('title', 'Untitled')
                
                # Extract text
                text = self.extract_page_text()
                
                results.append({
                    'url': url,
                    'title': title,
                    'text': text
                })
                
            except Exception as e:
                logger.error(f"Error extracting text from tab {tab.get('id')}: {e}")
                results.append({
                    'url': tab.get('url', 'Unknown URL'),
                    'title': tab.get('title', 'Untitled'),
                    'text': f"Error extracting text: {str(e)}"
                })
        
        # Reconnect to the original tab if possible
        if current_tab_id:
            try:
                for tab in tabs:
                    if tab['id'] == current_tab_id and 'webSocketDebuggerUrl' in tab:
                        self.ws = websocket.create_connection(tab['webSocketDebuggerUrl'])
                        self.tab_id = current_tab_id
                        break
            except Exception:
                # If we can't reconnect to the original tab, just continue
                pass
        
        return results
    
    def save_all_tabs_to_file(self, results, output_dir="extracted_texts"):
        """Save extracted text from all tabs to a single file."""
        try:
            # Create output directory if it doesn't exist
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # Create a filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"all_chrome_tabs_{timestamp}.md"
            filepath = os.path.join(output_dir, filename)
            
            # Generate content with tab separators
            content = f"# Chrome Tabs Content\nExtracted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            
            for i, result in enumerate(results, 1):
                # Add a clear separator between tabs
                content += f"## {i}. {result['title']}\n"
                content += f"URL: {result['url']}\n\n"
                content += result['text'] + "\n\n"
                content += "---\n\n"  # Horizontal rule between tabs
            
            # Save the text
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            
            return filepath
        except Exception as e:
            logger.error(f"Error saving all tabs to file: {e}")
            return None
    
    def get_all_tabs(self):
        """Get a list of all open tabs in Chrome"""
        try:
            # Get available tabs
            response = requests.get(f"http://{self.host}:{self.port}/json")
            if response.status_code != 200:
                return []
            
            tabs = response.json()
            
            # Filter to include only page-type tabs (exclude devtools, extensions)
            return [tab for tab in tabs if tab['type'] == 'page']
        except Exception as e:
            logger.error(f"Error getting tabs: {e}")
            return []

    def extract_page_text(self):
        """Extract structured text from the current page optimized for Confluence content"""
        script = """
        (function() {
            // Helper function to determine if element is visible
            function isVisible(element) {
                if (!element) return false;
                const style = window.getComputedStyle(element);
                return style.display !== 'none' && 
                    style.visibility !== 'hidden' && 
                    style.opacity !== '0' &&
                    element.offsetWidth > 0 &&
                    element.offsetHeight > 0;
            }
            
            // Helper function to extract text with proper structure
            function extractStructuredText(element) {
                if (!element) return '';
                
                // Clone the element to avoid modifying the original DOM
                const clone = element.cloneNode(true);
                
                // Remove unwanted elements
                const selectorsToRemove = [
                    'nav', 'header', '.aui-header', '#header', '.confluence-navigation',
                    '.footer', 'footer', '#footer', '.ia-secondary-header', '.ia-secondary-content-sidebar',
                    '.ads', '.advertisement', '.cookie', '.popup', '.modal',
                    'iframe', 'script', 'style', 'noscript', '#navigation',
                    '.hidden-content', '#likes-and-labels-container'
                ];
                
                selectorsToRemove.forEach(selector => {
                    clone.querySelectorAll(selector).forEach(el => el.remove());
                });
                
                // Extract Confluence page metadata if available
                let metadata = '';
                const title = document.querySelector('#title-text') || document.querySelector('h1.pagetitle');
                if (title) {
                    metadata += `# ${title.textContent.trim()}\\n\\n`;
                }
                
                const breadcrumbs = document.querySelector('#breadcrumbs');
                if (breadcrumbs) {
                    metadata += `Path: ${breadcrumbs.textContent.replace(/\\s+/g, ' ').trim()}\\n\\n`;
                }
                
                const pageInfo = document.querySelector('#page-metadata-info');
                if (pageInfo) {
                    metadata += `${pageInfo.textContent.replace(/\\s+/g, ' ').trim()}\\n\\n`;
                }
                
                // Special handling for Confluence code blocks
                clone.querySelectorAll('div.code, pre.syntaxhighlighter-pre, div.codeContent, div.syntaxhighlighter').forEach(codeBlock => {
                    // Try to determine language from class
                    let language = '';
                    const classes = codeBlock.className.split(' ');
                    for (const cls of classes) {
                        if (cls.startsWith('brush:')) {
                            language = cls.split(':')[1];
                            break;
                        } else if (['java', 'python', 'js', 'xml', 'sql', 'bash', 'shell', 'cpp', 'csharp'].includes(cls)) {
                            language = cls;
                            break;
                        }
                    }
                    
                    // Mark code blocks with backticks for Markdown
                    codeBlock.textContent = '```' + language + '\\n' + codeBlock.textContent.trim() + '\\n```';
                    
                    // Preserve formatting by wrapping code blocks
                    const wrapper = document.createElement('div');
                    wrapper.className = 'preserved-code-block';
                    codeBlock.parentNode.insertBefore(wrapper, codeBlock);
                    wrapper.appendChild(codeBlock);
                });
                
                // Handle Confluence panels (note, warning, info, etc.)
                clone.querySelectorAll('.confluence-information-macro, .panel, .aui-message').forEach(panel => {
                    let panelType = '';
                    if (panel.classList.contains('confluence-information-macro-tip') || panel.classList.contains('aui-message-success')) {
                        panelType = 'TIP:';
                    } else if (panel.classList.contains('confluence-information-macro-note') || panel.classList.contains('aui-message-info')) {
                        panelType = 'NOTE:';
                    } else if (panel.classList.contains('confluence-information-macro-warning') || panel.classList.contains('aui-message-warning')) {
                        panelType = 'WARNING:';
                    } else if (panel.classList.contains('confluence-information-macro-error') || panel.classList.contains('aui-message-error')) {
                        panelType = 'ERROR:';
                    } else {
                        panelType = 'INFO:';
                    }
                    
                    // Insert panel type at the beginning
                    const panelContent = panel.textContent.trim();
                    panel.textContent = `> ${panelType} ${panelContent}`;
                });
                
                // Handle Confluence status macros
                clone.querySelectorAll('.status-macro').forEach(status => {
                    const statusText = status.textContent.trim();
                    const statusColor = status.classList.contains('status-green') ? 'SUCCESS' : 
                                        status.classList.contains('status-red') ? 'FAILED' : 
                                        status.classList.contains('status-yellow') ? 'WARNING' : 'INFO';
                    status.textContent = `[STATUS: ${statusColor}] ${statusText}`;
                });
                
                // Preserve heading structure with Markdown-style formatting
                Array.from(clone.querySelectorAll('h1, h2, h3, h4, h5, h6')).forEach(heading => {
                    const level = parseInt(heading.tagName[1]);
                    const hashes = '#'.repeat(level);
                    heading.textContent = `${hashes} ${heading.textContent.trim()}`;
                    
                    // Add extra line before headings
                    const spacer = document.createElement('div');
                    spacer.textContent = '\\n';
                    heading.parentNode.insertBefore(spacer, heading);
                });
                
                // Handle tables better for Confluence
                clone.querySelectorAll('table.confluenceTable, table.aui').forEach(table => {
                    const textTable = document.createElement('div');
                    textTable.className = 'text-table';
                    
                    // Extract headers - Confluence specific
                    const headers = Array.from(table.querySelectorAll('th')).map(th => th.textContent.trim());
                    
                    // Extract rows
                    const rows = Array.from(table.querySelectorAll('tr')).map(tr => 
                        Array.from(tr.querySelectorAll('td')).map(td => td.textContent.trim())
                    ).filter(row => row.length > 0);
                    
                    // Create text representation
                    let tableText = '\\n';
                    if (headers.length > 0) {
                        tableText += headers.join(' | ') + '\\n';
                        tableText += headers.map(() => '---').join(' | ') + '\\n';
                    }
                    
                    rows.forEach(row => {
                        tableText += row.join(' | ') + '\\n';
                    });
                    
                    textTable.textContent = tableText + '\\n';
                    table.parentNode.replaceChild(textTable, table);
                });
                
                // Handle Confluence lists (may have specific classes)
                clone.querySelectorAll('ul.confluenceList, ol.confluenceList, ul, ol').forEach(list => {
                    const items = list.querySelectorAll('li');
                    Array.from(items).forEach((item, index) => {
                        const isOrdered = list.tagName.toLowerCase() === 'ol';
                        const marker = isOrdered ? `${index + 1}. ` : '- ';
                        item.textContent = marker + item.textContent.trim();
                    });
                });
                
                // Get the text content with preserved structure
                let content = metadata + clone.innerText;
                
                // Clean up excessive whitespace while preserving structure
                content = content.replace(/\\n\\s*\\n\\s*\\n+/g, '\\n\\n');
                
                return content;
            }
            
            // Confluence-specific selectors to try first
            const confluenceSelectors = [
                '#main-content',
                '#content',
                '.wiki-content',
                '.confluence-content',
                '#main',
                '.pageSection',
                '#page-content',
                '.aui-page-panel-content'
            ];
            
            // Try Confluence selectors first
            for (const selector of confluenceSelectors) {
                const elements = document.querySelectorAll(selector);
                for (const element of elements) {
                    if (isVisible(element) && element.textContent.trim().length > 100) {
                        return extractStructuredText(element);
                    }
                }
            }
            
            // Fall back to generic selectors if Confluence selectors don't find anything
            const genericSelectors = [
                'article', 'main', '.article-content', '.article-body', 
                '.content', '.main-content', '.post-content'
            ];
            
            // Try each generic selector
            for (const selector of genericSelectors) {
                const elements = document.querySelectorAll(selector);
                for (const element of elements) {
                    if (isVisible(element) && element.textContent.trim().length > 200) {
                        return extractStructuredText(element);
                    }
                }
            }
            
            // If nothing found, try the document body
            return extractStructuredText(document.body);
        })();
        """
        
        # Execute the script
        result = self.execute_script(script)
        
        # Additional Python-side post-processing
        if result:
            # Clean up common leftover artifacts
            result = self._post_process_text(result)
        
        return result or "No content could be extracted."
    
    def _post_process_text(self, text):
        """
        Post-process the extracted text to improve it for Confluence-based Copilot prompts
        """
        # Fix potential issues with code blocks
        text = re.sub(r'```\s*```', '', text)  # Remove empty code blocks
        
        # Make sure code blocks have language hints when possible
        code_block_patterns = {
            r'```\s*function': '```javascript\nfunction',
            r'```\s*def\s': '```python\ndef ',
            r'```\s*import': '```python\nimport',
            r'```\s*class\s': '```python\nclass ',
            r'```\s*(public|private)\s': '```java\n\\1 ',
            r'```\s*\<\?php': '```php\n<?php',
            r'```\s*package\s': '```java\npackage ',
            r'```\s*#include': '```cpp\n#include',
            r'```\s*using namespace': '```cpp\nusing namespace',
            r'```\s*const\s\w+\s=': '```javascript\nconst ',
            r'```\s*var\s\w+\s=': '```javascript\nvar ',
            r'```\s*let\s\w+\s=': '```javascript\nlet ',
            r'```\s*SELECT\s': '```sql\nSELECT ',
            r'```\s*<!DOCTYPE': '```html\n<!DOCTYPE',
            r'```\s*<html': '```html\n<html',
            # Confluence-specific code patterns
            r'```\s*@': '```java\n@',      # Java annotations
            r'```\s*---': '```yaml\n---',  # YAML frontmatter
            r'```\s*apiVersion': '```yaml\napiVersion', # Kubernetes YAML
            r'```\s*\<\?xml': '```xml\n<?xml'  # XML declarations
        }
        
        for pattern, replacement in code_block_patterns.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        # Fix confluence-specific formatting issues
        text = re.sub(r'JIRA:\s*([A-Z]+-\d+)', r'JIRA: [\1]', text)  # Format JIRA references
        text = re.sub(r'@([a-zA-Z0-9.-]+)', r'@\1', text)  # Preserve @ mentions
        
        # Clean up Confluence macro remnants
        text = re.sub(r'\{[a-zA-Z]+(?:\:[a-zA-Z]+)?\}.*?\{[a-zA-Z]+\}', '', text)
        
        # Ensure documentation comments are formatted properly
        text = re.sub(r'```\s*\/\*\*', '```java\n/**', text)
        text = re.sub(r'```\s*\/\*', '```java\n/*', text)
        text = re.sub(r'```\s*#', '```python\n#', text)
        
        # Handle Confluence's double dash that might be interpreted as strikethrough
        text = re.sub(r'(\w)--(\w)', r'\1—\2', text)
        
        # Make sure lists are properly formatted
        text = re.sub(r'\n\s*-\s+', '\n- ', text)
        text = re.sub(r'\n\s*(\d+)\.\s+', '\n\\1. ', text)
        
        # Fix heading formatting
        text = re.sub(r'([^#])\n#\s', '\\1\n\n# ', text)
        text = re.sub(r'([^#])\n##\s', '\\1\n\n## ', text)
        text = re.sub(r'([^#])\n###\s', '\\1\n\n### ', text)
        
        # Cleanup duplicated line breaks
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Add breaks between sections to improve readability
        text = re.sub(r'(# .+)\n([^\n#])', '\\1\n\n\\2', text)
        
        return text
    
    def close(self):
        """Close the connection"""
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
            self.ws = None


def launch_chrome_with_debugging(port=9222, user_data_dir=None):
    """
    Launch Google Chrome with remote debugging enabled.
    
    Args:
        port (int): The port to use for remote debugging.
        user_data_dir (str, optional): Path to Chrome user data directory.
    
    Returns:
        subprocess.Popen: The process object for the launched Chrome instance.
    """
    # Determine the Chrome executable path based on platform
    chrome_path = None
    system = platform.system()
    
    if system == "Linux":
        chrome_path = "google-chrome"
    elif system == "Darwin":  # macOS
        chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    elif system == "Windows":
        # Check common installation paths on Windows
        paths = [
            os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Google/Chrome/Application/chrome.exe'),
            os.path.join(os.environ.get('PROGRAMFILES', ''), 'Google/Chrome/Application/chrome.exe'),
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google/Chrome/Application/chrome.exe')
        ]
        for path in paths:
            if os.path.exists(path):
                chrome_path = path
                break
    
    if chrome_path is None:
        raise FileNotFoundError("Could not find Google Chrome executable. Please install Chrome.")
    
    # Set up command line arguments
    cmd = [chrome_path, 
           f"--remote-debugging-port={port}",
           "--remote-allow-origins=*"  # Add this flag to allow all origins
          ]
    
    # Add user data directory if specified
    if user_data_dir:
        cmd.append(f"--user-data-dir={user_data_dir}")
    else:
        # Create a temporary user data directory to avoid conflicts
        temp_dir = os.path.join(os.path.expanduser("~"), ".chrome_automation")
        os.makedirs(temp_dir, exist_ok=True)
        cmd.append(f"--user-data-dir={temp_dir}")
    
    # Add other useful flags
    cmd.extend([
        "--no-first-run",
        "--no-default-browser-check",
        "--start-maximized"
    ])
    
    # Launch Chrome
    try:
        process = subprocess.Popen(cmd)
        print(f"Chrome launched with remote debugging at port {port}")
        # Give Chrome a moment to start up
        time.sleep(2)
        return process
    except Exception as e:
        print(f"Error launching Chrome: {e}")
        return None


    def save_text_to_file(self, url, text, output_dir="extracted_texts"):
        """Save extracted text to a file in a format optimal for Confluence pages."""
        try:
            # Create output directory if it doesn't exist
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # Create a more descriptive filename from the URL
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.replace("www.", "")
            
            # For Confluence URLs, extract space and page name
            path_parts = parsed_url.path.strip("/").split("/")
            if "confluence" in domain:
                # Try to identify Confluence page structure
                # Typical format: /display/SPACE/Page+Name or /wiki/spaces/SPACE/pages/123456/Page+Name
                space_name = "unknown"
                page_name = "page"
                
                if "display" in path_parts:
                    display_index = path_parts.index("display")
                    if len(path_parts) > display_index + 2:
                        space_name = path_parts[display_index + 1]
                        page_name = path_parts[display_index + 2].replace("+", "_")
                elif "spaces" in path_parts:
                    spaces_index = path_parts.index("spaces")
                    if len(path_parts) > spaces_index + 1:
                        space_name = path_parts[spaces_index + 1]
                        # Find the page name after "pages" segment
                        if "pages" in path_parts[spaces_index:]:
                            pages_index = path_parts.index("pages", spaces_index)
                            if len(path_parts) > pages_index + 2:
                                page_name = path_parts[-1].replace("+", "_")
                
                # Use space and page name in filename
                filename = f"confluence_{space_name}_{page_name}.md"
            else:
                # For non-Confluence URLs
                path = parsed_url.path.strip("/").replace("/", "_")
                if not path:
                    path = "home"
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{domain}_{path}_{timestamp}.md"
            
            # Ensure valid filename
            filename = re.sub(r'[\\/*?:"<>|]', "_", filename)
            filepath = os.path.join(output_dir, filename)
            
            # Add a header with metadata for better context
            header = f"""# Content from {url}
    Extracted: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    Source: {domain}{parsed_url.path}

    """
            # Save the text with the header
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(header + text)
            
            return filepath
        except Exception as e:
            logger.error(f"Error saving text to file: {e}")
            return None


class WebToTextGUI:
    def __init__(self, root):
        """Initialize the GUI"""
        self.root = root
        self.root.title("WebToText - URL Text Extractor")
        self.root.geometry("800x700")
        
        # Chrome process and debugger
        self.chrome_process = None
        self.debugger = None
        
        # Configure styles
        style = ttk.Style()
        style.configure("TButton", padding=6)
        
        # Main layout frame
        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Chrome control section
        chrome_frame = ttk.LabelFrame(main_frame, text="Chrome Control", padding="5")
        chrome_frame.pack(fill=tk.X, pady=5)
        
        self.port_var = tk.StringVar(value="9222")
        ttk.Label(chrome_frame, text="Debug Port:").pack(side=tk.LEFT, padx=5)
        ttk.Entry(chrome_frame, textvariable=self.port_var, width=6).pack(side=tk.LEFT, padx=5)
        
        self.chrome_btn = ttk.Button(chrome_frame, text="Start Chrome", command=self.toggle_chrome)
        self.chrome_btn.pack(side=tk.LEFT, padx=5)
        
        self.connect_btn = ttk.Button(chrome_frame, text="Connect to Chrome", command=self.connect_to_chrome)
        self.connect_btn.pack(side=tk.LEFT, padx=5)
        
        self.status_var = tk.StringVar(value="Not connected")
        ttk.Label(chrome_frame, textvariable=self.status_var).pack(side=tk.RIGHT, padx=5)
        
        # URL input section
        ttk.Label(main_frame, text="Enter URL:").pack(anchor=tk.W, pady=(10, 5))
        
        url_frame = ttk.Frame(main_frame)
        url_frame.pack(fill=tk.X, pady=5)
        
        self.url_var = tk.StringVar()
        url_entry = ttk.Entry(url_frame, textvariable=self.url_var)
        url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        ttk.Button(url_frame, text="Extract", command=self.extract_text).pack(side=tk.RIGHT)
        
        # Options frame
        options_frame = ttk.Frame(main_frame)
        options_frame.pack(fill=tk.X, pady=5)
        
        self.save_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Save to file", variable=self.save_var).pack(side=tk.LEFT)
        
        self.output_dir = tk.StringVar(value="extracted_texts")
        ttk.Button(options_frame, text="Output Directory", 
                  command=self.select_output_dir).pack(side=tk.LEFT, padx=10)
        
        # Results section
        ttk.Label(main_frame, text="Extracted Text:").pack(anchor=tk.W, pady=(10, 5))
        
        self.results_text = scrolledtext.ScrolledText(main_frame, height=20)
        self.results_text.pack(fill=tk.BOTH, expand=True, pady=5)
        self.results_text.config(wrap=tk.WORD)

        # Add to the options_frame section:
        self.all_tabs_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Extract All Tabs", 
                variable=self.all_tabs_var).pack(side=tk.LEFT, padx=10)
        
        # Bottom buttons
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(bottom_frame, text="Clear", command=self.clear_text).pack(side=tk.LEFT)
        ttk.Button(bottom_frame, text="Help", 
                  command=self.show_help).pack(side=tk.RIGHT)
        
        # Bind window close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def toggle_chrome(self):
        """Start or stop Chrome process"""
        if self.chrome_process:
            self.chrome_process.terminate()
            self.chrome_process = None
            self.chrome_btn.config(text="Start Chrome")
            self.status_var.set("Chrome stopped")
            if self.debugger:
                self.debugger.close()
                self.debugger = None
        else:
            try:
                port = int(self.port_var.get())
                self.chrome_process = launch_chrome_with_debugging(port=port)
                if self.chrome_process:
                    self.chrome_btn.config(text="Stop Chrome")
                    self.status_var.set(f"Chrome started on port {port}")
                else:
                    self.status_var.set("Failed to start Chrome")
            except ValueError:
                messagebox.showerror("Invalid Port", "Please enter a valid port number")
    
    def connect_to_chrome(self):
        """Connect to running Chrome instance"""
        try:
            port = int(self.port_var.get())
            if self.debugger:
                self.debugger.close()
            
            self.debugger = ChromeRemoteDebugger(port=port)
            success, message = self.debugger.connect()
            
            if success:
                self.status_var.set(f"Connected to Chrome (port {port})")
            else:
                self.status_var.set(message)
                self.debugger = None
                messagebox.showerror("Connection Error", message)
        except ValueError:
            messagebox.showerror("Invalid Port", "Please enter a valid port number")
    
    def extract_text(self):
        """Extract text from the specified URL or all tabs"""
        if not self.debugger:
            # Try to connect first
            self.connect_to_chrome()
            if not self.debugger:
                messagebox.showerror("Not Connected", 
                                    "Not connected to Chrome. Please start Chrome and connect first.")
                return
        
        # Clear previous results
        self.clear_text()
        
        # Check if we're in all-tabs mode
        if self.all_tabs_var.get():
            self.results_text.insert(tk.END, "Extracting text from all open Chrome tabs...\n\n")
            self.root.update_idletasks()
            
            # Process all tabs in a separate thread
            def extract_all_thread():
                try:
                    # Extract text from all tabs
                    results = self.debugger.extract_text_from_all_tabs()
                    
                    if not results:
                        self.results_text.delete(1.0, tk.END)
                        self.results_text.insert(tk.END, "No open tabs found or error getting tabs.\n")
                        return
                    
                    # Display summary
                    self.results_text.delete(1.0, tk.END)
                    self.results_text.insert(tk.END, f"Extracted text from {len(results)} tabs.\n\n")
                    
                    for i, result in enumerate(results, 1):
                        self.results_text.insert(tk.END, f"{i}. {result['title']} ({result['url']})\n")
                    
                    # Save to file if requested
                    if self.save_var.get():
                        filepath = self.debugger.save_all_tabs_to_file(results, self.output_dir.get())
                        if filepath:
                            self.results_text.insert(tk.END, f"\n\n--- Saved all tabs to {filepath} ---")
                
                except Exception as e:
                    self.results_text.insert(tk.END, f"Error: {str(e)}\n")
            
            threading.Thread(target=extract_all_thread, daemon=True).start()
        else:
            # Original single-URL extraction code
            url = self.url_var.get().strip()
            if not url:
                messagebox.showinfo("No URL", "Please enter a URL to extract text from.")
                return
            
            # Add http:// if not present
            if not url.startswith('http'):
                url = 'https://' + url
                self.url_var.set(url)
            
            self.results_text.insert(tk.END, f"Extracting text from {url}...\n\n")
            self.root.update_idletasks()
            
            # Process in a separate thread
            def extract_thread():
                try:
                    # Navigate to URL
                    success, message = self.debugger.navigate(url)
                    if not success:
                        self.results_text.insert(tk.END, f"Error: {message}\n")
                        return
                    
                    # Wait a bit for page to load
                    time.sleep(2)
                    
                    # Extract text
                    text = self.debugger.extract_page_text()
                    
                    # Display the text
                    self.results_text.delete(1.0, tk.END)
                    self.results_text.insert(tk.END, text)
                    
                    # Save to file if requested
                    if self.save_var.get():
                        filepath = self.debugger.save_text_to_file(url, text, self.output_dir.get())
                        if filepath:
                            self.results_text.insert(tk.END, f"\n\n--- Saved to {filepath} ---")
                
                except Exception as e:
                    self.results_text.insert(tk.END, f"Error: {str(e)}\n")
            
            threading.Thread(target=extract_thread, daemon=True).start()
        
    def select_output_dir(self):
        """Select output directory for saved files"""
        directory = filedialog.askdirectory(initialdir=self.output_dir.get())
        if directory:
            self.output_dir.set(directory)
    
    def clear_text(self):
        """Clear the results text area"""
        self.results_text.delete(1.0, tk.END)
    
    def show_help(self):
        """Show help information"""
        help_text = """WebToText Help

    1. Starting Chrome:
    - Click "Start Chrome" to launch Chrome with remote debugging
    - Or start Chrome manually with: 
        google-chrome --remote-debugging-port=9222 --remote-allow-origins=*
    
    2. Connecting:
    - Click "Connect to Chrome" to connect to the running instance
    - Ensure the port number matches (default: 9222)
    
    3. Extracting Text:
    - Single Page: Enter a URL and click "Extract"
    - All Open Tabs: Check "Extract All Tabs" and click "Extract"
    
    4. Saving:
    - Check "Save to file" to save extracted text
    - For single URLs, saves to individual files
    - For all tabs, saves to a single file with clear separators
    - Click "Output Directory" to change where files are saved
    
    Note: Starting Chrome through this app creates a separate profile.
    For using existing logins, start Chrome manually with the remote debugging flag.
    """
        messagebox.showinfo("WebToText Help", help_text)
    
    def on_closing(self):
        """Handle window closing event"""
        if self.chrome_process:
            self.chrome_process.terminate()
        if self.debugger:
            self.debugger.close()
        self.root.destroy()


def main():
    # Check for required packages
    try:
        import websocket
        import requests
    except ImportError:
        print("Required packages not found. Please install them with:")
        print("pip install websocket-client requests")
        sys.exit(1)
    
    root = tk.Tk()
    app = WebToTextGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()