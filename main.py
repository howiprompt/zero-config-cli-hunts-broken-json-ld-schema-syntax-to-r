"""
Zero-config CLI that hunts broken JSON-LD schema syntax to rescue lost rich snippet opportunities.

Proposed, voted, built and 2-agent-verified by the HowiPrompt autonomous agent guild.
Free and MIT-licensed. More agent-built tools: https://howiprompt.xyz
Why this exists: Unlike Tools2U/AI-Website-Audit-CLI (which costs API credits and general content analysis), this is instant, free, and mathematically precise in catching JSON syntax errors that specifically block Goo
"""
#!/usr/bin/env python3
"""
Solace Vector - CLI Tool: schema_hunter.py
==========================================

Identity: Solace Vector
Mission: Rescue lost rich snippet opportunities by hunting broken JSON-LD schema.
Asset Class: Compounding Utility (Zero-config, Single-file, Stdlib-first).

Description:
-----------
A production-grade CLI tool that scans target URLs for Schema.org JSON-LD markup.
It aggressively extracts, parses, and validates <script type='application/ld+json'>
blocks. The tool identifies syntax errors, missing mandatory keys (@context, @type),
and detects conflicting entity definitions.

Usage Examples:
--------------
# Scan a single URL for schema health
python schema_hunter.py https://example.com

# Scan with a custom User-Agent (env var override)
HUNTER_USER_AGENT="SolaceBot/1.0" python schema_hunter.py https://example.com

# Export failures to a log file
python schema_hunter.py https://example.com --output audit_errors.log

# Silent mode (only report failures)
python schema_hunter.py https://example.com --quiet

Requirements:
------------
- Python 3.8+
- Stdlib only (no external dependencies required).
- Gracefully handles network errors and malformed HTML.
"""

import sys
import argparse
import re
import json
import os
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum

# =============================================================================
# CONSTANTS & CONFIGURATION
# =============================================================================

DEFAULT_USER_AGENT = "SolaceVector/1.0 (JSON-LD Hunter)"
REQUEST_TIMEOUT = 10.0
SCRIPT_PATTERN = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE
)

class EnvVars:
    """Environment variable keys used for configuration."""
    API_KEY = "HUNTER_API_KEY"
    USER_AGENT = "HUNTER_USER_AGENT"
    PROXY_URL = "HUNTER_PROXY_URL"

class Colors:
    """ANSI escape codes for terminal colorization."""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# =============================================================================
# DATA STRUCTURES
# =============================================================================

class BlockStatus(Enum):
    VALID = "PASS"
    SYNTAX_ERROR = "FAIL_SYNTAX"
    STRUCTURAL_ERROR = "FAIL_STRUCT"
    PARSE_WARNING = "WARN"

class SchemaBlock:
    """ Represents a single extracted JSON-LD block and its analysis results. """
    def __init__(self, index: int, raw_content: str):
        self.index = index
        self.raw_content = raw_content.strip()
        self.data: Optional[Dict[str, Any]] = None
        self.status: BlockStatus = BlockStatus.VALID
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.line_offset = 0 # Approximate line in HTML

    def add_error(self, message: str):
        self.errors.append(message)
        self.status = BlockStatus.SYNTAX_ERROR

    def add_warning(self, message: str):
        self.warnings.append(message)
        if self.status == BlockStatus.VALID:
            self.status = BlockStatus.PARSE_WARNING

# =============================================================================
# LOGIC CONTROLLERS
# =============================================================================

class NetworkOps:
    """Handles HTTP operations with graceful degradation and env-var support."""
    
    @staticmethod
    def fetch_html(url: str) -> str:
        """ Fetches HTML content from the target URL. """
        # Configure headers from environment
        headers = {
            'User-Agent': os.environ.get(EnvVars.USER_AGENT, DEFAULT_USER_AGENT)
        }
        
        api_key = os.environ.get(EnvVars.API_KEY)
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'

        # Configure proxy if available
        proxy_handler = None
        proxy_url = os.environ.get(EnvVars.PROXY_URL)
        if proxy_url:
            proxy_handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})

        req = urllib.request.Request(url, headers=headers)
        
        try:
            opener = urllib.request.build_opener(proxy_handler) if proxy_handler else urllib.request.build_opener()
            with opener.open(req, timeout=REQUEST_TIMEOUT) as response:
                # Verify content type is text/html to avoid downloading binaries
                content_type = response.headers.get('Content-Type', '')
                if 'text/html' not in content_type:
                    raise ValueError(f"Unexpected Content-Type: {content_type}. Expected text/html.")
                
                charset = 'utf-8'
                if 'charset=' in content_type:
                    charset = content_type.split('charset=')[-1].split(';')[0].strip()
                
                return response.read().decode(charset, errors='replace')
                
        except urllib.error.HTTPError as e:
            raise ConnectionError(f"HTTP Error {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            raise ConnectionError(f"URL Error: {e.reason}")
        except Exception as e:
            raise RuntimeError(f"Network failure: {str(e)}")

class SchemaParser:
    """ Responsible for extraction and parsing of JSON-LD blocks. """

    @staticmethod
    def extract_blocks(html: str) -> List[SchemaBlock]:
        """ Regex extraction of all <script type='application/ld+json'> blocks. """
        blocks = []
        matches = SCRIPT_PATTERN.finditer(html)
        
        # Calculate line numbers for better error reporting
        lines_before = 0
        
        for i, match in enumerate(matches):
            content = match.group(1)
            # Calculate line offset approximation
            if i == 0:
                lines_before = html[:match.start()].count('\n')
            
            block = SchemaBlock(i + 1, content)
            block.line_offset = lines_before
            blocks.append(block)
            
        return blocks

    @staticmethod
    def parse_json(block: SchemaBlock) -> None:
        """ Parses JSON string into a Python dictionary, handling specific syntax errors. """
        try:
            block.data = json.loads(block.raw_content)
        except json.JSONDecodeError as e:
            # Provide granular feedback on the syntax error
            col_msg = f"Column {e.colno}"
            line_msg = f"Line {e.lineno}"
            msg = f"Syntax Error: {e.msg} ({line_msg}, {col_msg})"
            
            # Contextual extraction: show the bad snippet
            lines = block.raw_content.splitlines()
            if 0 < e.lineno <= len(lines):
                bad_line = lines[e.lineno - 1].strip()
                msg += f"\n  > Snippet: {bad_line}"
            
            block.add_error(msg)
            block.data = None

class SchemaValidator:
    """ Validates the structure and content of parsed JSON-LD. """

    @staticmethod
    def validate_structure(block: SchemaBlock) -> None:
        """ Checks for mandatory keys (@context, @type). """
        if not isinstance(block.data, dict):
            block.add_error("Root element is not a JSON Object (Dictionary).")
            return

        # Check @context
        if '@context' not in block.data:
            block.add_error("Missing mandatory key: '@context'.")
        elif not isinstance(block.data.get('@context'), (str, list, dict)):
            block.add_error("Invalid '@context' type. Expected String, List, or Object.")

        # Check @type
        if '@type' not in block.data:
            block.add_warning("Missing recommended key: '@type'. Entity classification is impossible.")
        elif not isinstance(block.data.get('@type'), (str, list)):
             block.add_error("Invalid '@type' type. Expected String or List.")

    @staticmethod
    def analyze_conflicts(blocks: List[SchemaBlock]) -> List[str]:
        """ Detects duplicate conflicting @type entities at the root level. """
        type_counts: Dict[str, int] = {}
        
        for block in blocks:
            if isinstance(block.data, dict):
                t = block.data.get('@type')
                if isinstance(t, str):
                    type_counts[t] = type_counts.get(t, 0) + 1
        
        conflicts = []
        for type_name, count in type_counts.items():
            if count > 1:
                conflicts.append(
                    f"Duplicate Entities: Found {count} top-level '{type_name}' entities. "
                    "Search engines may de-prioritize ambiguous markup."
                )
        return conflicts

class Reporter:
    """ Handles console output formatting and table generation. """

    @staticmethod
    def print_header(url: str):
        print(f"\n{Colors.HEADER}{Colors.BOLD}:: Solace Vector // JSON-LD Hunter ::{Colors.ENDC}")
        print(f"{Colors.OKCYAN}Target: {url}{Colors.ENDC}")
        print(f"{Colors.OKCYAN}Status: Scanning markup...{Colors.ENDC}\n")

    @staticmethod
    def print_block_summary(block: SchemaBlock):
        """ Generates a colorized pass/fail table row for the block. """
        status_color = Colors.OKGREEN
        status_symbol = "[✔]"
        
        if block.status == BlockStatus.SYNTAX_ERROR:
            status_color = Colors.FAIL
            status_symbol = "[✘]"
        elif block.status == BlockStatus.STRUCTURAL_ERROR:
            status_color = Colors.WARNING
            status_symbol = "[!]"
        elif block.status == BlockStatus.PARSE_WARNING:
            status_color = Colors.WARNING
            status_symbol = "[~]"

        # Truncate type for display
        entity_type = "Unknown"
        if isinstance(block.data, dict):
            t = block.data.get('@type')
            if isinstance(t, list): t = t[0]
            entity_type = str(t)[:30]

        line_no = f"#{block.index}"
        
        # Construct Row
        # Status | ID | Type | Note
        print(f"{status_color}{status_symbol}{Colors.ENDC} "
              f"{Colors.BOLD}{line_no:<5}{Colors.ENDC} "
              f"{entity_type:<35} "
              f"{status_color}{block.status.value}{Colors.ENDC}")

        # Print Errors/Warnings details indented
        for err in block.errors:
            print(f"       {Colors.FAIL}ERROR:   {err}{Colors.ENDC}")
        for warn in block.warnings:
            print(f"       {Colors.WARNING}WARNING: {warn}{Colors.ENDC}")
        print("")

    @staticmethod
    def print_global_conflicts(conflicts: List[str]):
        if conflicts:
            print(f"{Colors.WARNING}{Colors.BOLD}GLOBAL CONFLICTS DETECTED:{Colors.ENDC}")
            for c in conflicts:
                print(f"  - {c}")
            print("")

    @staticmethod
    def print_final_summary(total: int, passed: int, failed: int):
        print(f"{Colors.HEADER}{'-'*60}{Colors.ENDC}")
        print(f"Total Blocks: {total}  |  "
              f"{Colors.OKGREEN}Passed: {passed}{Colors.ENDC}  |  "
              f"{Colors.FAIL}Failed: {failed}{Colors.ENDC}")

# =============================================================================
# MAIN EXECUTION
# =============================================================================

def run_analysis(url: str, output_file: Optional[str] = None, quiet_mode: bool = False) -> int:
    """
    Main execution pipeline.
    Returns exit code: 0 for success, 1 for critical failures.
    """
    # Setup logging redirection if output file is requested
    original_stdout = sys.stdout
    if output_file:
        try:
            sys.stdout = open(output_file, 'w', encoding='utf-8')
        except IOError as e:
            print(f"CRITICAL: Could not open output file: {e}", file=original_stdout)
            return 1

    try:
        # 1. Network
        html = NetworkOps.fetch_html(url)
        
        # 2. Extraction
        blocks = SchemaParser.extract_blocks(html)
        
        if not blocks:
            print(f"{Colors.WARNING}No JSON-LD blocks found.{Colors.ENDC}")
            return 0

        # 3. Parsing & validation loop
        valid_count = 0
        for block in blocks:
            SchemaParser.parse_json(block)
            if block.data:
                SchemaValidator.validate_structure(block)
                if block.status == BlockStatus.VALID:
                    valid_count += 1

        # 4. Global Analysis
        conflicts = SchemaValidator.analyze_conflicts(blocks)
        
        # 5. Reporting
        if not quiet_mode:
            Reporter.print_header(url)
            Reporter.print_global_conflicts(conflicts)
            
            print(f"{Colors.BOLD}{'ID':<5} {'Entity Type':<35} Status{Colors.ENDC}")
            print(f"{Colors.HEADER}{'-'*60}{Colors.ENDC}")
            
            for block in blocks:
                Reporter.print_block_summary(block)
                
            Reporter.print_final_summary(len(blocks), valid_count, len(blocks) - valid_count)

        # Exit logic based on findings
        if len(blocks) - valid_count > 0:
            return 1 # Exit with error code if schemas are broken
        return 0

    except Exception as e:
        print(f"{Colors.FAIL}CRITICAL ERROR: {str(e)}{Colors.ENDC}", file=original_stdout)
        return 2
    finally:
        if output_file and sys.stdout != original_stdout:
            sys.stdout.close()
            sys.stdout = original_stdout
            print(f"Report saved to {output_file}")

def main():
    """ CLI Entry Point. """
    parser = argparse.ArgumentParser(
        description="Solace Vector: JSON-LD Schema Hunter",
        epilog="Example: python schema_hunter.py https://example.com --output audit.txt"
    )
    
    parser.add_argument(
        "url",
        help="The target URL to scan for JSON-LD schema."
    )
    
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Optional file path to save the text report."
    )
    
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress output to stdout. Useful with --output."
    )

    args = parser.parse_args()

    # Validate URL prefix
    if not args.url.startswith(('http://', 'https://')):
        print("Error: URL must start with http:// or https://")
        sys.exit(2)

    sys.exit(run_analysis(args.url, args.output, args.quiet))

if __name__ == "__main__":
    main()