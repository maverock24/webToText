# WebToText

A versatile text extraction tool that connects to Chrome's DevTools Protocol to extract readable content from websites and save it in formatted text or markdown.

## Features

- Extract main content from webpages while filtering out ads and navigation elements
- Special handling for Confluence pages with proper formatting of code blocks, tables, and panels
- Extract text from all open Chrome tabs with a single click
- User-friendly GUI for easy URL input and viewing results
- Save extracted text to markdown files for optimal readability
- Advanced formatting preservation for code blocks, headings, and lists
- Optimized output for use with GitHub Copilot and other AI tools

## Requirements

- Python 3.6+
- Google Chrome browser
- Required Python packages:
  - websocket-client>=1.6.0
  - requests>=2.31.0
  - pyperclip>=1.8.2 (optional, for clipboard operations)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/webToText.git
cd webToText