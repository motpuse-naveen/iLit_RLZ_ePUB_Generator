#!/usr/bin/env python3
"""
Script to generate EPUB from the JS content file
"""

import json
import os
import shutil
import zipfile
from pathlib import Path
import re
from datetime import datetime
import argparse
import ast

# Configuration
SOURCE_DIR = Path(__file__).parent

# Default configuration for this script. These can be overridden dynamically
# via CLI arguments or metadata in the input JSON.
DEFAULT_INPUT_DIR_NAME = "default_input_dir"
DEFAULT_BOOK_TITLE = "Book Title"
DEFAULT_BOOK_ID = "Book_Id"
DEFAULT_BOOK_AUTHOR = "Book Author"

# Name of the main CSS file inside the EPUB package
EPUB_CSS_NAME = "styles.css"

CUSTOM_CSS_NAME = "custom.css"

# Runtime configuration (initialized in main())
INPUT_DIR = None
BOOK_TITLE = None
BOOK_ID = None
BOOK_AUTHOR = None
BOOK_PREFIX = None

JS_FILE = None
MEDIA_DIR = None
FONTS_SOURCE_DIR = None
COVER_SOURCE_NAME = None

# EPUB output locations (initialized in main())
OUTPUT_ROOT_DIR_NAME = "Final_ePUB"
EPUB_DIR = None
EPUB_NAME = None
CUSTOM_CSS_FILE = SOURCE_DIR / CUSTOM_CSS_NAME
DEFAULT_CSS_FILE = None

# EPUB structure directories
OEBPS_DIR_NAME = "OPS"
XHTML_DIR_NAME = "xhtml"
IMAGES_DIR_NAME = "images"
FONTS_DIR_NAME = "fonts"
CSS_DIR_NAME = "css"

# These are derived from EPUB_DIR during initialization
OEBPS_DIR = None
METAINF_DIR = None
OEBPS_MEDIA_DIR = None
OEBPS_FONTS_DIR = None
OEBPS_XHTML_DIR = None
OEBPS_CSS_DIR = None


def parse_args():
    """Parse command-line arguments for the EPUB generator."""
    parser = argparse.ArgumentParser(description="Generate EPUB from an input content folder.")
    parser.add_argument(
        "input_dir",
        nargs="?",
        default=DEFAULT_INPUT_DIR_NAME,
        help=(
            "Input folder (parallel to this script by default) that contains the JS file, "
            "a media/ directory, and an optional fonts/ directory."
        ),
    )
    parser.add_argument(
        "--output-root",
        default=OUTPUT_ROOT_DIR_NAME,
        help="Output root directory (default: Final_ePUB). Can be absolute or relative to the script.",
    )
    parser.add_argument(
        "--title",
        help="Override book title (otherwise taken from JSON or default).",
    )
    parser.add_argument(
        "--book-id",
        help="Override book id / ISBN (otherwise taken from JSON or default).",
    )
    parser.add_argument(
        "--author",
        help="Override book author (otherwise taken from JSON or default).",
    )
    return parser.parse_args()


def extract_text_from_html(html_content):
    """
    Extract text content from HTML, cleaning z tags and other formatting.
    Removes z tags, converts <br> to spaces, and strips whitespace.
    """
    if not html_content:
        return None
    
    # Remove z tags (opening and closing)
    text = re.sub(r"<z\s+class=['\"]s['\"]>", '', html_content)
    text = re.sub(r'<z\s+class=["\']w["\']>', '', text)
    text = re.sub(r'</z>', '', text)
    
    # Convert <br> and <br /> to spaces
    text = re.sub(r'<br\s*/?\s*>', ' ', text, flags=re.IGNORECASE)
    
    # Extract text content from HTML tags (remove all HTML tags)
    text = re.sub(r'<[^>]+>', '', text)
    
    # Clean up whitespace: normalize multiple spaces to single space
    text = re.sub(r'\s+', ' ', text)
    
    # Strip leading/trailing whitespace
    text = text.strip()
    
    return text if text else None


def extract_metadata_from_json(data, default_title, default_id, default_author):
    """
    Best-effort extraction of basic metadata from the JSON content.
    Priority order:
    1. Extract from Pages.tp HTML (title from <h1 class='title'>, author from <h1 class='author'>)
    2. Use top-level BookTitle/Title and BookAuthor/Author fields
    3. Fall back to provided defaults
    """
    title = None
    author = None
    
    # First, try to extract from title page (Pages.tp)
    pages = data.get("Pages", {})
    tp_page = pages.get("tp")
    if tp_page:
        sentences = tp_page.get("sentences", [])
        for sentence in sentences:
            sentence_text = sentence.get("sentence_text", "")
            if not sentence_text:
                continue
            
            # Extract title from <h1 class='title'>
            if 'class=\'title\'' in sentence_text or 'class="title"' in sentence_text:
                if title is None:  # Only extract first match
                    title = extract_text_from_html(sentence_text)
            
            # Extract author from <h1 class='author'>
            if 'class=\'author\'' in sentence_text or 'class="author"' in sentence_text:
                if author is None:  # Only extract first match
                    author = extract_text_from_html(sentence_text)
    
    # Fall back to top-level fields if title page extraction didn't work
    if not title:
        title = (
            data.get("BookTitle")
            or data.get("Title")
            or default_title
        )
    
    if not author:
        author = (
            data.get("BookAuthor")
            or data.get("Author")
            or default_author
        )
    
    # Book ID extraction with fallback to Styles array
    book_id = (
        data.get("BookId")
        or data.get("BookID")
        or data.get("ISBN")
    )
    
    # If not found, extract from first CSS filename in Styles array
    if not book_id:
        styles = data.get("Styles", [])
        if styles and isinstance(styles, list) and len(styles) > 0:
            first_css = styles[0]
            if isinstance(first_css, str):
                # Remove extension (.css) to get Book ID
                book_id = Path(first_css).stem
    
    # Final fallback to default
    if not book_id:
        book_id = default_id
    
    return title, book_id, author


def init_config(input_dir_path: Path, book_title: str, book_id: str, book_author: str, output_root: Path):
    """
    Initialise global paths and identifiers based on the chosen input
    directory and metadata.
    """
    global INPUT_DIR, BOOK_TITLE, BOOK_ID, BOOK_AUTHOR, BOOK_PREFIX
    global JS_FILE, MEDIA_DIR, FONTS_SOURCE_DIR
    global EPUB_DIR, EPUB_NAME
    global OEBPS_DIR, METAINF_DIR, OEBPS_MEDIA_DIR, OEBPS_FONTS_DIR, OEBPS_XHTML_DIR, OEBPS_CSS_DIR
    global DEFAULT_CSS_FILE

    INPUT_DIR = input_dir_path
    BOOK_TITLE = book_title
    BOOK_ID = book_id
    BOOK_AUTHOR = book_author
    BOOK_PREFIX = f"{BOOK_ID}_"

    # Source locations (within the input directory)
    JS_FILE = input_dir_path / f"{input_dir_path.name}.js"
    MEDIA_DIR = input_dir_path / "media"
    FONTS_SOURCE_DIR = input_dir_path / FONTS_DIR_NAME

    # DEFAULT_CSS_FILE is no longer needed - we use Styles array directly
    # Keeping it for backward compatibility but it won't be used if Styles exists
    DEFAULT_CSS_FILE = f"{BOOK_ID}.css"

    # Resolve and create output root
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    # EPUB directory and filename: BookTitle_BookID (with spaces replaced by underscores)
    sanitized_title = BOOK_TITLE.replace(" ", "_")
    epub_base_name = f"{sanitized_title}_{BOOK_ID}"
    EPUB_DIR = output_root / epub_base_name
    EPUB_NAME = f"{epub_base_name}.epub"

    # Derived EPUB sub-directories
    OEBPS_DIR = EPUB_DIR / OEBPS_DIR_NAME
    METAINF_DIR = EPUB_DIR / "META-INF"
    OEBPS_MEDIA_DIR = OEBPS_DIR / IMAGES_DIR_NAME
    OEBPS_FONTS_DIR = OEBPS_DIR / FONTS_DIR_NAME
    OEBPS_XHTML_DIR = OEBPS_DIR / XHTML_DIR_NAME
    OEBPS_CSS_DIR = OEBPS_DIR / CSS_DIR_NAME


def parse_js_file(js_file: Path):
    """Parse the JS file and extract JSON content.

    The input file is a JS object literal of the form:
        var content = { ... };
    with unquoted keys. We normalise it into valid JSON first.
    """
    print(f"Reading JS file: {js_file}")
    with open(js_file, 'r', encoding='utf-8') as f:
        raw = f.read()

    # Strip the leading variable assignment and trailing semicolon/newlines
    if raw.lstrip().startswith("var content"):
        raw = raw[raw.index("{") :]
    raw = raw.strip()
    if raw.endswith(";"):
        raw = raw[:-1].rstrip()

    # The remaining text is a JS-style object literal with unquoted keys,
    # single-quoted strings, and trailing commas. Convert it to a Python
    # literal (which is more permissive than JSON) in a best-effort way:
    #   1) Quote bare keys:  Styles: [...] -> "Styles": [...]
    #   2) Keep existing string quoting as-is (single or double).
    def quote_keys(text: str) -> str:
        # Match keys at object depth:   identifier:  OR  "identifier":
        pattern = re.compile(r'(?P<pre>[\{\s,])(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:')

        def _repl(m: re.Match) -> str:
            return f'{m.group("pre")}"{m.group("key")}":'

        return pattern.sub(_repl, text)

    py_like = quote_keys(raw)

    # literal_eval can handle single/double quotes and most trailing commas
    data = ast.literal_eval(py_like)
    return data

def create_epub_structure():
    """Create EPUB directory structure"""
    print("Creating EPUB structure...")
    
    # Remove existing EPUB directory if it exists
    if EPUB_DIR.exists():
        shutil.rmtree(EPUB_DIR)
    
    # Create directories
    OEBPS_DIR.mkdir(parents=True, exist_ok=True)
    METAINF_DIR.mkdir(parents=True, exist_ok=True)
    OEBPS_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    # Fonts are now stored under css/fonts/, so we do not need a top-level
    # OPS/fonts directory inside the EPUB structure.
    OEBPS_XHTML_DIR.mkdir(parents=True, exist_ok=True)
    OEBPS_CSS_DIR.mkdir(parents=True, exist_ok=True)
    
    return OEBPS_DIR, METAINF_DIR, OEBPS_MEDIA_DIR, OEBPS_FONTS_DIR, OEBPS_XHTML_DIR, OEBPS_CSS_DIR

def fix_image_paths(html_content, page_id):
    """Fix image paths in HTML content"""
    # Replace the long path with ../images/ to match POC_ePUB structure
    # INPUT_DIR is a Path pointing to the input folder; we only want its name
    # when matching within the HTML content.
    input_dir_name = INPUT_DIR.name if isinstance(INPUT_DIR, Path) else str(INPUT_DIR)
    html_content = re.sub(
        rf'{re.escape(input_dir_name)}/media/',
        f'../{IMAGES_DIR_NAME}/',
        html_content
    )
    
    # Also fix any direct references to images/ (should be ../images/)
    html_content = re.sub(
        r'src=["\']images/',
        r'src="../images/',
        html_content
    )

    # If we have a known cover source image name, normalize any references to it
    # to use the standard cover.jpg inside the EPUB.
    if COVER_SOURCE_NAME:
        html_content = html_content.replace(
            f'../{IMAGES_DIR_NAME}/{COVER_SOURCE_NAME}',
            f'../{IMAGES_DIR_NAME}/cover.jpg',
        )

    return html_content

def clean_html_tags(html_content):
    """Remove invalid <z> tags entirely, keeping only the text content"""
    # Remove opening <z class='s'> tags
    html_content = re.sub(r"<z\s+class=['\"]s['\"]>", '', html_content)
    
    # Remove opening <z class="w"> tags
    html_content = re.sub(r'<z\s+class=["\']w["\']>', '', html_content)
    
    # Remove all closing </z> tags
    html_content = re.sub(r'</z>', '', html_content)
    
    # Fix TOC links: convert old .htm filenames to .xhtml
    # Replace href="0822452596_XXX.htm" with href="XXX.xhtml"
    html_content = re.sub(
        rf'href="{re.escape(BOOK_PREFIX)}([^"]+)\.htm"',
        r'href="\1.xhtml"',
        html_content
    )

    
    return html_content

def add_aria_hidden_to_br_hr(html_content):
    """Add aria-hidden=\"true\" to <br> and <hr> elements so they are hidden from screen readers."""
    if not html_content:
        return html_content
    # <br> or <br /> or <br ...attrs...> - add aria-hidden="true" if not present
    html_content = re.sub(
        r'<br(\s[^>]*?)?\s*/?>',
        lambda m: _add_aria_hidden_to_self_closing(m.group(0), 'br', m.group(1) or ''),
        html_content
    )
    # <hr> or <hr /> or <hr ...attrs...> - add aria-hidden="true" if not present
    html_content = re.sub(
        r'<hr(\s[^>]*?)?\s*/?>',
        lambda m: _add_aria_hidden_to_self_closing(m.group(0), 'hr', m.group(1) or ''),
        html_content
    )
    return html_content

def _add_aria_hidden_to_self_closing(full_tag, tag_name, existing_attrs):
    """Ensure tag has aria-hidden=\"true\" and return the full tag string."""
    if 'aria-hidden' in existing_attrs:
        return full_tag
    # Add aria-hidden="true" before closing /> or >
    if existing_attrs.strip():
        new_attrs = f'{existing_attrs} aria-hidden="true"'
    else:
        new_attrs = ' aria-hidden="true"'
    return f'<{tag_name}{new_attrs} />'

def convert_copyright_structure(html_content, page_id, page_number):
    """
    Convert copyright page structure to match POC_ePUB:
    - Convert <p class='nonindent1'> to <h1>
    - Convert <p class='nonindent'> with "Bestellers" to <h2>
    - Group consecutive list-item paragraphs into <ul class="bestellers_list"><li> structures
    - Reassign all IDs sequentially to avoid duplicates and ensure correct order
    """
    if page_id != 'crt' and not page_id.startswith('copyright'):
        return html_content
    
    # Convert <p class='nonindent1'> to <h1>
    html_content = re.sub(
        r'<p\s+class=["\']nonindent1["\']([^>]*)>(.*?)</p>',
        r'<h1\1>\2</h1>',
        html_content,
        flags=re.DOTALL
    )
    
    # Convert <p class='nonindent'> with "Bestellers" to <h2>
    html_content = re.sub(
        r'<p\s+class=["\']nonindent["\']([^>]*)>(.*?Bestellers[^<]*?)</p>',
        r'<h2\1>\2</h2>',
        html_content,
        flags=re.DOTALL | re.IGNORECASE
    )
    
    # Now convert consecutive paragraphs (that aren't headings or special classes) to <ul><li>
    lines = html_content.split('\n')
    result_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Check if this is a paragraph that could be a list item
        p_match = re.search(r'<p([^>]*)>(.*?)</p>', line, re.DOTALL)
        if p_match and not re.search(r'class=["\'](nonindent|crt)', p_match.group(1)):
            attrs = p_match.group(1)
            content = p_match.group(2).strip()
            
            # Skip if content is just whitespace or non-breaking space
            if content and content not in ['&#x00A0;', '&nbsp;', '']:
                # Collect consecutive list items
                list_items = []
                j = i
                
                while j < len(lines):
                    current_line = lines[j]
                    current_p_match = re.search(r'<p([^>]*)>(.*?)</p>', current_line, re.DOTALL)
                    
                    # Stop if we hit a heading, special paragraph, or non-paragraph element
                    if (re.search(r'<h[1-6]', current_line) or 
                        (current_p_match and re.search(r'class=["\'](nonindent|crt)', current_p_match.group(1))) or
                        (not current_p_match and current_line.strip())):
                        break
                    
                    if current_p_match:
                        current_attrs = current_p_match.group(1)
                        current_content = current_p_match.group(2).strip()
                        if current_content and current_content not in ['&#x00A0;', '&nbsp;', '']:
                            list_items.append(current_content)
                            j += 1
                            continue
                    break
                
                # If we found 2+ consecutive list items, convert to <ul><li>
                if len(list_items) >= 2:
                    result_lines.append('            <ul class="bestellers_list">')
                    for li_content in list_items:
                        result_lines.append(f'                <li>{li_content}</li>')
                    result_lines.append('            </ul>')
                    i = j  # Skip processed lines
                    continue
        
        result_lines.append(line)
        i += 1
    
    # Convert result_lines back to HTML string for further processing
    converted_html = '\n'.join(result_lines)
    
    # Split HTML into head and body sections - only process body content
    head_match = re.search(r'(<head>.*?</head>)', converted_html, re.DOTALL | re.IGNORECASE)
    body_match = re.search(r'(<body>.*?</body>)', converted_html, re.DOTALL | re.IGNORECASE)
    
    if not body_match:
        # Fallback: process entire content but skip head-like tags
        body_content = converted_html
        head_content = ''
    else:
        head_content = head_match.group(1) if head_match else ''
        body_content = body_match.group(1)
    
    # Reassign all IDs sequentially to avoid duplicates and ensure correct order
    # Only process body content
    page_num = page_number if page_number else 3
    element_counter = 0
    current_ul_id = None
    li_counter = 0
    body_lines = body_content.split('\n')
    final_body_lines = []
    in_head_section = False
    
    for line in body_lines:
        # Track if we're still in head section (shouldn't happen, but safety check)
        if re.search(r'<head', line, re.IGNORECASE):
            in_head_section = True
            final_body_lines.append(line)
            continue
        if re.search(r'</head', line, re.IGNORECASE):
            in_head_section = False
            final_body_lines.append(line)
            continue
        
        # Skip head section entirely
        if in_head_section:
            final_body_lines.append(line)
            continue
        
        # Skip pagebreak span - it keeps its own ID (pagebreak_X)
        if 'pagebreak' in line or ('sr-only' in line and 'pagebreak' in line):
            final_body_lines.append(line)
            continue
        
        # Skip link, meta, script, style tags (shouldn't be in body, but safety check)
        if re.search(r'<(link|meta|script|style|title)', line, re.IGNORECASE):
            final_body_lines.append(line)
            continue
        
        # Handle <ul> tags - assign sequential ID
        ul_match = re.search(r'<ul([^>]*)>', line, re.IGNORECASE)
        if ul_match:
            element_counter += 1
            current_ul_id = f'page_{page_num}_{element_counter}'
            li_counter = 0
            attrs = ul_match.group(1)
            # Remove existing id
            attrs = re.sub(r'\s+id=["\'][^"\']+["\']', '', attrs)
            # Add new id
            if attrs.strip():
                new_attrs = f'{attrs} id="{current_ul_id}"'
            else:
                new_attrs = f' id="{current_ul_id}"'
            line = re.sub(r'<ul[^>]*>', f'<ul{new_attrs}>', line, flags=re.IGNORECASE)
        
        # Handle <li> tags - use nested ID format: page_X_Y_Z
        li_match = re.search(r'<li([^>]*)>', line, re.IGNORECASE)
        if li_match:
            li_counter += 1
            if current_ul_id:
                new_li_id = f'{current_ul_id}_{li_counter}'
                attrs = li_match.group(1)
                # Remove existing id
                attrs = re.sub(r'\s+id=["\'][^"\']+["\']', '', attrs)
                # Add new id
                if attrs.strip():
                    new_attrs = f'{attrs} id="{new_li_id}"'
                else:
                    new_attrs = f' id="{new_li_id}"'
                line = re.sub(r'<li[^>]*>', f'<li{new_attrs}>', line, flags=re.IGNORECASE)
            else:
                # Fallback if no ul context (shouldn't happen)
                element_counter += 1
                new_li_id = f'page_{page_num}_{element_counter}'
                attrs = li_match.group(1)
                attrs = re.sub(r'\s+id=["\'][^"\']+["\']', '', attrs)
                if attrs.strip():
                    new_attrs = f'{attrs} id="{new_li_id}"'
                else:
                    new_attrs = f' id="{new_li_id}"'
                line = re.sub(r'<li[^>]*>', f'<li{new_attrs}>', line, flags=re.IGNORECASE)
        
        # Handle other block elements: h1, h2, p, div, section
        # Skip if already processed as ul/li
        if not ul_match and not li_match:
            def replace_element_id(match):
                nonlocal element_counter
                tag = match.group('tag')
                attrs = match.group('attrs') or ''
                
                # Skip nested elements and head tags
                if tag.lower() in ['span', 'strong', 'em', 'a', 'br', 'sup', 'link', 'meta', 'script', 'style', 'title']:
                    return match.group(0)
                
                element_counter += 1
                new_id = f'page_{page_num}_{element_counter}'
                
                # Remove existing id
                attrs = re.sub(r'\s+id=["\'][^"\']+["\']', '', attrs)
                # Add new id
                if attrs.strip():
                    new_attrs = f'{attrs} id="{new_id}"'
                else:
                    new_attrs = f' id="{new_id}"'
                
                return f'<{tag}{new_attrs}>'
            
            line = re.sub(
                r'<(?P<tag>h[1-6]|p|div|section)(?P<attrs>(?:\s+[^>]*?)?)>',
                replace_element_id,
                line,
                flags=re.IGNORECASE
            )
        
        final_body_lines.append(line)
    
    # Reassemble HTML: head (unchanged) + processed body
    processed_body = '\n'.join(final_body_lines)
    
    if head_match and body_match:
        # Replace body section with processed version in the converted HTML
        converted_html = converted_html.replace(body_match.group(1), processed_body)
        return converted_html
    else:
        # Fallback: return processed body if we couldn't find sections
        return processed_body

def ensure_unique_ids(html_content, page_number, element_counter):
    """
    Ensure all top-level block elements in HTML content have unique IDs.
    Elements without IDs will get IDs following the pattern: page_{page_number}_{counter}
    Elements with existing IDs will be preserved.
    Only processes block-level elements (p, h1-h6, div, etc.) that appear at the top level.
    """
    if not html_content or not html_content.strip():
        return html_content, element_counter
    
    # Elements that should have IDs (block-level elements)
    # Focus on elements that are typically top-level content elements
    elements_needing_ids = {'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'section', 'article', 
                           'nav', 'header', 'footer', 'aside', 'main', 'ul', 'ol', 'li', 
                           'dl', 'dt', 'dd', 'blockquote', 'figure', 'figcaption', 'table',
                           'thead', 'tbody', 'tfoot', 'tr'}
    
    # Pattern to match opening tags at the start of the string or after whitespace/newline
    # This helps identify top-level elements (not nested)
    # Match: whitespace/newline followed by <tag ...> or <tag .../>
    tag_pattern = re.compile(
        r'(?P<prefix>^|\s+)<(?P<tag>\w+)(?P<attrs>(?:\s+[^>]*?)?)(?P<self_closing>/?)>',
        re.MULTILINE | re.DOTALL
    )
    
    def add_id_to_tag(match):
        nonlocal element_counter
        prefix = match.group('prefix')
        tag = match.group('tag').lower()
        attrs = match.group('attrs')
        self_closing = match.group('self_closing')
        original_tag = match.group('tag')  # Preserve original case
        
        # Only process elements that should have IDs
        if tag not in elements_needing_ids:
            return match.group(0)
        
        # Check if ID already exists
        id_match = re.search(r'\bid\s*=\s*["\']([^"\']+)["\']', attrs, re.IGNORECASE)
        if id_match:
            # ID already exists, keep it
            return match.group(0)
        
        # Add unique ID
        element_counter += 1
        unique_id = f'page_{page_number}_{element_counter}'
        
        # Insert ID attribute
        if attrs.strip():
            # Add ID after existing attributes
            new_attrs = f'{attrs} id="{unique_id}"'
        else:
            # No existing attributes, just add ID with a space
            new_attrs = f' id="{unique_id}"'
        
        return f'{prefix}<{original_tag}{new_attrs}{self_closing}>'
    
    # Process all tags in the content
    result = tag_pattern.sub(add_id_to_tag, html_content)
    
    return result, element_counter

def generate_html_page(page_id, page_data, toc_entry, css_file, page_number=None):
    """Generate HTML file for a page"""
    sentences = page_data.get('sentences', [])
    
    # Determine epub:type and section class based on page_id
    epub_type = "bodymatter chapter"
    section_class = "page-container"
    if page_id == 'cvi' or page_id.startswith('cover'):
        epub_type = "frontmatter cover"
    elif page_id == 'tp' or page_id.startswith('titlepage'):
        epub_type = "frontmatter titlepage"
    elif page_id == 'crt' or page_id.startswith('copyright'):
        epub_type = "frontmatter copyright"
    elif page_id == 'content':
        epub_type = "frontmatter content"
    elif page_id.startswith('glossary'):
        epub_type = "glossary"
        section_class = "glossary"
    
    # Build HTML content (HTML5 standard) - matching POC_ePUB structure
    html_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE html>',
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en">',
        '',
        '<head>',
        '    <meta charset="utf-8" />',
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>',
        f'    <title>{toc_entry.get("title", page_id)}</title>',
        f'    <link rel="stylesheet" type="text/css" href="../css/{css_file}" />',
        # Project-specific overrides (replaces legacy epub_common.css)
        *( [f'    <link rel="stylesheet" type="text/css" href="../css/{CUSTOM_CSS_NAME}" />'] if CUSTOM_CSS_FILE.exists() else [] ),
        '</head>',
        '',
        '<body>',
        '    <main role="main">',
        f'        <section id="page_{page_number if page_number else page_id}" epub:type="{epub_type}" class="{section_class}">'
    ]
    
    # Initialize element counter for unique IDs (starts at 0, pagebreak will be 1)
    element_counter = 0
    
    # Add page break marker at the start if page number is provided
    if page_number is not None:
        element_counter += 1
        pagebreak_id = f"pagebreak_{page_number}"
        page_label = f"Page {page_number}"
        if page_id == 'cvi' or page_id.startswith('cover'):
            page_label = "Cover Page"
        html_parts.append(f'            <span epub:type="pagebreak" role="doc-pagebreak" id="{pagebreak_id}"><span class="sr-only">{page_label}</span></span>')
    
    # Special handling for cover page
    if page_id == 'cvi' or page_id.startswith('cover'):
        # Add h1 with visually-hidden class
        element_counter += 1
        cover_h1_text = f'Book cover of "{BOOK_TITLE}" by {BOOK_AUTHOR}'
        html_parts.append(f'            <h1 id="page_{page_number if page_number else 1}_{element_counter}" class="visually-hidden">{cover_h1_text}</h1>')
    
    # Add all sentences and ensure unique IDs
    for idx, sentence in enumerate(sentences, start=1):
        sentence_text = sentence.get('sentence_text', '')
        if sentence_text:
            # Fix image paths
            sentence_text = fix_image_paths(sentence_text, page_id)
            # Clean invalid HTML tags (convert z tags to span)
            sentence_text = clean_html_tags(sentence_text)
            # Add aria-hidden="true" to <br> and <hr> so they are hidden from screen readers
            sentence_text = add_aria_hidden_to_br_hr(sentence_text)
            
            # Special handling for cover page images - update alt text
            if (page_id == 'cvi' or page_id.startswith('cover')) and '<img' in sentence_text:
                # Use &quot; so alt="...\"...\"..." is valid (no unescaped " inside attribute)
                cover_alt_text = f'Book cover of &quot;{BOOK_TITLE}&quot; by {BOOK_AUTHOR}'
                # Update or add alt text to image
                if 'alt=' in sentence_text:
                    # Replace existing alt text
                    sentence_text = re.sub(
                        r'alt=["\']([^"\']*)["\']',
                        f'alt="{cover_alt_text}"',
                        sentence_text
                    )
                else:
                    # Add alt text before closing />
                    sentence_text = re.sub(
                        r'(<img[^>]*?)(\s*/?>)',
                        f'\\1 alt="{cover_alt_text}"\\2',
                        sentence_text
                    )
            
            # Ensure all elements have unique IDs
            if page_number is not None:
                sentence_text, element_counter = ensure_unique_ids(sentence_text, page_number, element_counter)
            html_parts.append(f'            {sentence_text}')
    
    # Convert copyright page structure to match POC_ePUB (headings and lists)
    if page_id == 'crt' or page_id.startswith('copyright'):
        # Join all HTML parts, convert structure, then split back
        combined_html = '\n'.join(html_parts)
        combined_html = convert_copyright_structure(combined_html, page_id, page_number)
        html_parts = combined_html.split('\n')
    
    # Title page: change h1.author to p.author so the page has only one h1 (the book title)
    if page_id == 'tp' or page_id.startswith('titlepage'):
        combined_html = '\n'.join(html_parts)
        # Replace <h1 ... class='author' ...>...</h1> with <p ... class='author' ...>...</p>
        combined_html = re.sub(
            r'<h1((?=[^>]*class=["\']author["\'])[^>]*)>(.*?)</h1>',
            r'<p\1>\2</p>',
            combined_html,
            flags=re.DOTALL
        )
        html_parts = combined_html.split('\n')
    
    html_parts.extend([
        '        </section>',
        '    </main>',
        '</body>',
        '',
        '</html>'
    ])
    
    return '\n'.join(html_parts)

def create_mimetype():
    """Create mimetype file (must be first, uncompressed)"""
    mimetype_path = EPUB_DIR / "mimetype"
    with open(mimetype_path, 'w', encoding='utf-8') as f:
        f.write('application/epub+zip')
    return mimetype_path

def create_container_xml(metainf_dir):
    """Create META-INF/container.xml"""
    container_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="{OEBPS_DIR_NAME}/package.opf" media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>'''
    
    container_path = metainf_dir / "container.xml"
    with open(container_path, 'w', encoding='utf-8') as f:
        f.write(container_xml)
    
    return container_path

def get_image_media_type(img_file):
    img_path = Path(img_file)
    ext = img_path.suffix.lower()
    return {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.svg': 'image/svg+xml',
        '.webp': 'image/webp',
    }.get(ext, 'image/jpeg')


def create_content_opf(data, toc_entries, oebps_dir):
    """Create OEBPS/package.opf"""
    
    # Get all pages
    pages = data.get('Pages', {})
    
    # Build manifest items
    manifest_items = []
    spine_items = []
    
    # Add CSS (always named styles.css inside the EPUB)
    css_file = EPUB_CSS_NAME
    manifest_items.append(f'    <item id="css" href="css/{css_file}" media-type="text/css"/>')
    
    # Add EPUB 3.0 navigation document (toc.xhtml) - matches POC_ePUB structure
    manifest_items.append(f'    <item id="toc" href="xhtml/toc.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
    
    # Check if content.xhtml will be added from TOC entries (to avoid duplicates)
    has_content_in_toc = 'content' in toc_entries or 'toc' in toc_entries
    
    # Add content.xhtml (visible table of contents page) only if not already in TOC
    if not has_content_in_toc:
        manifest_items.append(f'    <item id="content" href="xhtml/content.xhtml" media-type="application/xhtml+xml"/>')
    
    # Add NCX file for backward compatibility (required when spine has toc="ncx")
    manifest_items.append(f'    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')
    
    # Add cover image entries using standardised names to match POC EPUB:
    #   - images/cover.jpg  (with properties="cover-image")
    #   - images/cover_thumbnail.jpg
    cover_media_type = get_image_media_type("cover.jpg")
    manifest_items.append(
        f'    <item id="cover-image" href="{IMAGES_DIR_NAME}/cover.jpg" media-type="{cover_media_type}" properties="cover-image"/>'
    )
    manifest_items.append(
        f'    <item id="thumbnailcover-image" href="{IMAGES_DIR_NAME}/cover_thumbnail.jpg" media-type="{cover_media_type}"/>'
    )
    
    # Add all images from media directory (original source images)
    if MEDIA_DIR.exists():
        for img_file in MEDIA_DIR.glob('*.jpg'):
            # Skip the original cover source file; we reference cover.jpg instead
            if COVER_SOURCE_NAME and img_file.name == COVER_SOURCE_NAME:
                continue
            media_type = get_image_media_type(img_file)
            manifest_items.append(f'    <item id="img-{img_file.stem}" href="{IMAGES_DIR_NAME}/{img_file.name}" media-type="{media_type}"/>')
    
    # Add audio files if they exist (for glossary with audio support)
    # Check source directory first, then target directory (in case already copied)
    audio_source_dir = INPUT_DIR / "audio"
    audio_target_dir = OEBPS_DIR / "audio"
    audio_dir_to_check = audio_target_dir if audio_target_dir.exists() else audio_source_dir
    if audio_dir_to_check.exists():
        for audio_file in audio_dir_to_check.glob('*.mp3'):
            manifest_items.append(f'    <item id="audio-{audio_file.stem}" href="audio/{audio_file.name}" media-type="audio/mpeg" />')
    
    # Add font files to manifest (look in input fonts directory first, then legacy locations).
    # Fonts are placed alongside CSS in a css/fonts/ subfolder so that the
    # original CSS src:url(fonts/...) references remain valid without changes.
    font_dir_to_use = None
    if FONTS_SOURCE_DIR and FONTS_SOURCE_DIR.exists():
        font_dir_to_use = FONTS_SOURCE_DIR
    else:
        fonts_dir = SOURCE_DIR / FONTS_DIR_NAME
        fonts_dir_alt = MEDIA_DIR / FONTS_DIR_NAME
        if fonts_dir.exists():
            font_dir_to_use = fonts_dir
        elif fonts_dir_alt.exists():
            font_dir_to_use = fonts_dir_alt
    
    if font_dir_to_use:
        for font_file in font_dir_to_use.glob('*.ttf'):
            font_name = font_file.name
            manifest_items.append(
                f'    <item id="font-{font_file.stem}" href="{CSS_DIR_NAME}/fonts/{font_name}" media-type="font/ttf"/>'
            )
    
    # Sort TOC entries by playOrder
    sorted_toc = sorted(toc_entries.items(), key=lambda x: int(x[1].get('playOrder', 999)))
    
    # Track if content is in TOC entries
    content_in_spine = False
    
    # Add HTML files
    for page_id, toc_entry in sorted_toc:
        href = toc_entry.get('href', f'{page_id}.htm')
        # Use the href from TOC but ensure it's in OEBPS
        html_file = href.replace(BOOK_PREFIX, '').replace('.htm', '.xhtml')
        # Default manifest ID is the page_id
        manifest_id = page_id
        
        # Map front matter file names to match POC_ePUB: cvi -> cover, tp -> titlepage, crt -> copyright
        if html_file == 'cvi.xhtml':
            html_file = 'cover.xhtml'
        elif html_file == 'tp.xhtml':
            html_file = 'titlepage.xhtml'
        elif html_file == 'crt.xhtml':
            html_file = 'copyright.xhtml'
        elif page_id == 'content' or page_id == 'toc':
            # Handle content/toc TOC entry - map to content.xhtml
            html_file = 'content.xhtml'
            # Use 'content' as the ID (not 'toc' which is reserved for navigation document)
            manifest_id = 'content'
            if toc_entry.get('linear') == 'yes':
                content_in_spine = True
        
        manifest_items.append(f'    <item id="{manifest_id}" href="xhtml/{html_file}" media-type="application/xhtml+xml"/>')
        if toc_entry.get('linear') == 'yes':
            spine_items.append(f'    <itemref idref="{manifest_id}"/>')
    
    # Ensure content.xhtml is in spine if not already added (matches POC_ePUB structure)
    if not content_in_spine and 'content' not in [item.split('"')[1] for item in spine_items if 'idref=' in item]:
        # Find position after copyright (crt) to insert content
        crt_index = None
        for i, item in enumerate(spine_items):
            if 'idref="crt"' in item or 'idref=\'crt\'' in item:
                crt_index = i + 1
                break
        if crt_index is not None:
            spine_items.insert(crt_index, '    <itemref idref="content"/>')
        else:
            # If crt not found, add after tp (titlepage)
            tp_index = None
            for i, item in enumerate(spine_items):
                if 'idref="tp"' in item or 'idref=\'tp\'' in item:
                    tp_index = i + 1
                    break
            if tp_index is not None:
                spine_items.insert(tp_index, '    <itemref idref="content"/>')
            else:
                # Fallback: add after cover
                cover_index = None
                for i, item in enumerate(spine_items):
                    if 'idref="cover"' in item or 'idref=\'cover\'' in item:
                        cover_index = i + 1
                        break
                if cover_index is not None:
                    spine_items.insert(cover_index, '    <itemref idref="content"/>')
                else:
                    # Last resort: add at beginning
                    spine_items.insert(0, '    <itemref idref="content"/>')
    
    publication_date = datetime.now().strftime("%Y-%m-%d")
    
    content_opf = f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xmlns:dc="http://purl.org/dc/elements/1.1/" xml:lang="en">
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
        <dc:title>{BOOK_TITLE}</dc:title>
        <dc:identifier id="bookid">{BOOK_ID}</dc:identifier>
        <dc:creator id="author">{BOOK_AUTHOR}</dc:creator>
        <meta refines="#author" property="role" scheme="marc:relators">aut</meta>
        <dc:publisher>Savvas Learning Company</dc:publisher>
        <dc:rights>Copyright © 2027</dc:rights>
        <dc:language>en</dc:language>
        <dc:date>{publication_date}</dc:date>
        <dc:type>Book</dc:type>
        <meta name="cover" content="cover-image"/>
        <meta property="dcterms:modified">{datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")}</meta>
        <meta property="schema:accessMode">textual</meta>
        <meta property="schema:accessMode">visual</meta>
        <meta property="schema:accessibilityFeature">alternativeText</meta>
        <meta property="schema:accessibilityFeature">readingOrder</meta>
        <meta property="schema:accessibilityFeature">structuralNavigation</meta>
        <meta property="schema:accessibilityHazard">none</meta>
        <meta property="pageBreakSource">Printed book</meta>
        <meta property="schema:accessModeSufficient">textual,visual</meta>
        <meta property="schema:accessModeSufficient">textual</meta>
        <meta property="rendition:spread">none</meta>
        <meta property="rendition:flow">scrolled-doc</meta>
        <meta property="schema:accessibilitySummary">
            This publication includes mark-up to enable accessibility and compatibility with assistive technology. 
            Images, audio, and video in the publication are well-described in conformance with WCAG 2.2 AA. Structural navigation may be inconsistent.
        </meta>
    </metadata>
    <manifest>
{chr(10).join(manifest_items)}
    </manifest>
    <spine toc="ncx">
{chr(10).join(spine_items)}
    </spine>
</package>'''
    
    opf_path = oebps_dir / "package.opf"
    with open(opf_path, 'w', encoding='utf-8') as f:
        f.write(content_opf)
    
    return opf_path

def create_toc_ncx(data, toc_entries, oebps_dir):
    """Create OPS/toc.ncx"""
    
    # Sort TOC entries by playOrder
    sorted_toc = sorted(toc_entries.items(), key=lambda x: int(x[1].get('playOrder', 999)))
    
    nav_points = []
    nav_counter = 1
    
    for page_id, toc_entry in sorted_toc:
        title = toc_entry.get('title', page_id)
        href = toc_entry.get('href', f'{page_id}.htm')
        html_file = href.replace(BOOK_PREFIX, '').replace('.htm', '.xhtml')
        # Map front matter file names
        if html_file == 'cvi.xhtml':
            html_file = 'cover.xhtml'
        elif html_file == 'tp.xhtml':
            html_file = 'titlepage.xhtml'
        elif html_file == 'crt.xhtml':
            html_file = 'copyright.xhtml'
        elif page_id == 'content' or page_id == 'toc':
            # Handle content/toc TOC entry - map to content.xhtml (not toc.xhtml)
            html_file = 'content.xhtml'
        play_order = toc_entry.get('playOrder', nav_counter)
        
        nav_points.append(f'''        <navPoint id="navpoint-{nav_counter}" playOrder="{play_order}">
            <navLabel>
                <text>{title}</text>
            </navLabel>
            <content src="xhtml/{html_file}"/>
        </navPoint>''')
        nav_counter += 1
    
    toc_ncx = f'''<?xml version="1.0" encoding="UTF-8"?>
                    <ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
                        <head>
                            <meta name="dtb:uid" content="{BOOK_ID}"/>
                            <meta name="dtb:depth" content="1"/>
                            <meta name="dtb:totalPageCount" content="0"/>
                            <meta name="dtb:maxPageNumber" content="0"/>
                        </head>
                        <docTitle>
                            <text>{BOOK_TITLE}</text>
                        </docTitle>
                        <navMap>
                    {chr(10).join(nav_points)}
                        </navMap>
                    </ncx>'''

    
    ncx_path = oebps_dir / "toc.ncx"
    with open(ncx_path, 'w', encoding='utf-8') as f:
        f.write(toc_ncx)
    
    return ncx_path

def create_nav_xhtml(data, toc_entries, oebps_xhtml_dir, css_file):
    """Create EPUB 3.0 toc.xhtml navigation document - matches POC_ePUB structure"""
    
    # Sort TOC entries by playOrder
    sorted_toc = sorted(toc_entries.items(), key=lambda x: int(x[1].get('playOrder', 999)))
    
    # Build TOC items (all pages) - matching POC_ePUB structure
    nav_items = []
    item_counter = 1
    for page_id, toc_entry in sorted_toc:
        title = toc_entry.get('title', page_id)
        href = toc_entry.get('href', f'{page_id}.htm')
        html_file = href.replace(BOOK_PREFIX, '').replace('.htm', '.xhtml')
        # Map front matter file names
        if html_file == 'cvi.xhtml':
            html_file = 'cover.xhtml'
        elif html_file == 'tp.xhtml':
            html_file = 'titlepage.xhtml'
        elif html_file == 'crt.xhtml':
            html_file = 'copyright.xhtml'
        elif page_id == 'content' or page_id == 'toc' or html_file == 'content.xhtml' or html_file == 'toc.xhtml':
            # Map content/toc entries to content.xhtml (the visible TOC page)
            html_file = 'content.xhtml'
        # Get page number from playOrder (used for anchor)
        page_num = toc_entry.get('playOrder', item_counter)
        nav_items.append(f'                    <li id="toc_list_{item_counter}"><a href="{html_file}#page_{page_num}">{title}</a></li>')
        item_counter += 1
    
    # Build optional custom.css link for toc.xhtml
    custom_link = ""
    if CUSTOM_CSS_FILE.exists():
        custom_link = f'    <link rel="stylesheet" type="text/css" href="../css/{CUSTOM_CSS_NAME}"/>\n'

    toc_xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en">

<head>
    <title>Table of Contents</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    <link rel="stylesheet" type="text/css" href="../css/{css_file}" />
    <meta charset="utf-8" />
{custom_link}</head>
<body>
    <main role="main">
        <section id="page_toc" epub:type="frontmatter toc" class="page-container">
            <nav id="toc" epub:type="toc" role="doc-toc" aria-labelledby="toc_title">
                <h1 id="toc_title">Table of Contents</h1>
                <ol id="toc_list">
{chr(10).join(nav_items)}
                </ol>
            </nav>
        </section>
    </main>
</body>

</html>'''
    
    toc_path = oebps_xhtml_dir / "toc.xhtml"
    with open(toc_path, 'w', encoding='utf-8') as f:
        f.write(toc_xhtml)
    
    return toc_path

def get_chapter_title_html_for_content(data, page_id):
    """
    Get the formatted chapter title HTML (with span.small1 etc.) from the chapter's
    first sentence (the h1.chapter heading). Used for content.xhtml so formatting matches POC.
    Returns None if not found; caller falls back to plain title.
    """
    pages = data.get('Pages', {})
    page_data = pages.get(page_id)
    if not page_data:
        return None
    sentences = page_data.get('sentences', [])
    if not sentences:
        return None
    first = sentences[0].get('sentence_text', '')
    if not first or 'class=\'chapter\'' not in first and 'class="chapter"' not in first:
        return None
    # Extract inner content of the h1
    inner_match = re.search(r'<h1[^>]*class=["\']chapter["\'][^>]*>(.*?)</h1>', first, re.DOTALL | re.IGNORECASE)
    if not inner_match:
        return None
    inner = inner_match.group(1)
    # Remove z tags (same as clean_html_tags but without the TOC link fix)
    inner = re.sub(r"<z\s+class=['\"]s['\"]>", '', inner)
    inner = re.sub(r'<z\s+class=["\']w["\']>', '', inner)
    inner = re.sub(r'</z>', '', inner)
    # Remove "CHAPTER" and number part: everything up to and including first <br> or <br />
    inner = re.sub(r'^.*?<br\s*/?\s*>', '', inner, count=1, flags=re.DOTALL | re.IGNORECASE)
    inner = inner.strip()
    if not inner:
        return None
    # Use small1 in content.xhtml (POC uses small1 for TOC links)
    inner = re.sub(r'\bclass=["\']small["\']', 'class="small1"', inner)
    # Ensure <br> in title have aria-hidden (same as elsewhere)
    inner = add_aria_hidden_to_br_hr(inner)
    return inner

def create_content_xhtml(data, toc_entries, oebps_xhtml_dir, css_file):
    """Create content.xhtml - the visible table of contents page with CONTENTS heading"""
    
    # Sort TOC entries by playOrder
    sorted_toc = sorted(toc_entries.items(), key=lambda x: int(x[1].get('playOrder', 999)))
    
    # Build TOC items (only chapters) - matching POC_ePUB structure with formatted titles
    nav_items = []
    item_counter = 1
    for page_id, toc_entry in sorted_toc:
        # Only include main content pages (chapters)
        if page_id.startswith('c') and page_id[1:].isdigit():
            title_plain = toc_entry.get('title', page_id)
            # Prefer formatted title (with span.small1 etc.) from chapter's first heading
            title_html = get_chapter_title_html_for_content(data, page_id)
            if title_html:
                title_display = title_html
            else:
                title_display = title_plain
            href = toc_entry.get('href', f'{page_id}.htm')
            html_file = href.replace(BOOK_PREFIX, '').replace('.htm', '.xhtml')
            # Map front matter file names
            if html_file == 'cvi.xhtml':
                html_file = 'cover.xhtml'
            elif html_file == 'tp.xhtml':
                html_file = 'titlepage.xhtml'
            elif html_file == 'crt.xhtml':
                html_file = 'copyright.xhtml'
            # Get page number from playOrder (used for anchor)
            page_num = toc_entry.get('playOrder', item_counter)
            nav_items.append(f'                        <li id="page_4_3_{item_counter}" class=\'toc\'><a class="hlink" href="{html_file}#page_{page_num}">{title_display}</a></li>')
            item_counter += 1
    
    # Build optional custom.css link for content.xhtml
    custom_link = ""
    if CUSTOM_CSS_FILE.exists():
        custom_link = f'    <link rel="stylesheet" type="text/css" href="../css/{CUSTOM_CSS_NAME}"/>\n'

    content_xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en">

<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    <title>Table of Content</title>
    <link rel="stylesheet" type="text/css" href="../css/{css_file}" />
{custom_link}</head>
<body>
    <main role="main">
        <section id="page_4" epub:type="frontmatter content" class="page-container">
            <span epub:type="pagebreak" role="doc-pagebreak" id="pagebreak_4"><span class="sr-only">Page 4</span></span>
            <nav id="page_4_1" aria-labelledby="page_4_2">
                <h1 id="page_4_2" class='chapter'>CONTENTS</h1>
                <ol id="page_4_3" class='toc-list'>
{chr(10).join(nav_items)}
                </ol>
            </nav>
        </section>
    </main>
</body>

</html>'''
    
    content_path = oebps_xhtml_dir / "content.xhtml"
    with open(content_path, 'w', encoding='utf-8') as f:
        f.write(content_xhtml)
    
    return content_path

def copy_font_files(oebps_fonts_dir):
    """Copy font files to EPUB structure"""
    print("Copying font files...")

    # Prefer fonts alongside the input content folder, fall back to legacy locations
    font_dir_to_use = None
    if FONTS_SOURCE_DIR and FONTS_SOURCE_DIR.exists():
        font_dir_to_use = FONTS_SOURCE_DIR
    else:
        fonts_dir = SOURCE_DIR / FONTS_DIR_NAME
        fonts_dir_alt = MEDIA_DIR / FONTS_DIR_NAME
        if fonts_dir.exists():
            font_dir_to_use = fonts_dir
        elif fonts_dir_alt.exists():
            font_dir_to_use = fonts_dir_alt
    
    if font_dir_to_use:
        font_files = list(font_dir_to_use.glob('*.ttf'))
        if font_files:
            # Place fonts under css/fonts so that src:url(fonts/...) works
            css_fonts_dir = OEBPS_CSS_DIR / "fonts"
            css_fonts_dir.mkdir(parents=True, exist_ok=True)
            for font_file in font_files:
                shutil.copy2(font_file, css_fonts_dir / font_file.name)
                print(f"  Copied {font_file.name} to css/fonts")
        else:
            print("  No .ttf font files found in fonts/ directory")
    else:
        print("  No fonts/ directory found (checked: ./fonts and ./media/fonts)")

def copy_media_files(oebps_media_dir, data):
    """Copy media files to EPUB structure and ensure cover assets exist."""
    print("Copying media files...")
    copied_files = []
    cover_source_input = None
    if MEDIA_DIR.exists():
        for file in MEDIA_DIR.iterdir():
            if file.is_file():
                # Only copy actual image assets, not CSS or other aux files
                suffix = file.suffix.lower()
                if suffix not in ('.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp'):
                    continue

                # If this is the original cover source file, keep note of it
                # but don't copy it directly; we'll normalise to cover.jpg.
                if COVER_SOURCE_NAME and file.name == COVER_SOURCE_NAME:
                    cover_source_input = file
                    continue

                target_path = oebps_media_dir / file.name
                shutil.copy2(file, target_path)
                copied_files.append(target_path.name)
                print(f"  Copied {file.name}")

    # Determine a suitable source image for cover.jpg / cover_thumbnail.jpg
    cover_source_path = None

    # 1) Prefer explicit CoverImage entry from JSON, if present (from input media)
    cover_image_info = data.get('CoverImage', {}).get('media_info', {})
    cover_src = cover_image_info.get('src')
    if cover_src:
        cover_name = os.path.basename(cover_src)
        candidate = MEDIA_DIR / cover_name
        if candidate.exists():
            cover_source_path = candidate

    # 2) Fallback: look for any file in images directory that looks like a cover
    if cover_source_path is None:
        for name in sorted(copied_files):
            lower = name.lower()
            if 'cvr' in lower or 'cover' in lower:
                candidate = oebps_media_dir / name
                if candidate.exists():
                    cover_source_path = candidate
                    break

    # 3) Fallback: specific files such as tp.jpg or first JPEG
    if cover_source_path is None:
        for name in sorted(copied_files):
            if name.lower() == 'tp.jpg':
                cover_source_path = oebps_media_dir / name
                break
    if cover_source_path is None:
        for name in sorted(copied_files):
            if name.lower().endswith('.jpg'):
                cover_source_path = oebps_media_dir / name
                break

    # 4) Create standardised cover.jpg and cover_thumbnail.jpg if possible
    if cover_source_path is not None:
        cover_jpg_path = oebps_media_dir / "cover.jpg"
        if not cover_jpg_path.exists():
            shutil.copy2(cover_source_path, cover_jpg_path)
            print(f"  Created cover.jpg from {cover_source_path.name}")

        cover_thumb_path = oebps_media_dir / "cover_thumbnail.jpg"
        if not cover_thumb_path.exists():
            shutil.copy2(cover_source_path, cover_thumb_path)
            print(f"  Created cover_thumbnail.jpg from {cover_source_path.name}")
    else:
        print("  Warning: Could not determine a cover image source; cover.jpg and cover_thumbnail.jpg were not created.")

def copy_css_file(data, oebps_css_dir):
    """Copy CSS files to EPUB structure"""
    print("Copying CSS files...")

    # 1️⃣ Copy main source CSS file into EPUB as styles.css
    # Use Styles array directly - it should always exist in the JSON
    css_files = data.get('Styles', [])
    if css_files and isinstance(css_files, list) and len(css_files) > 0:
        main_css = css_files[0]
    else:
        # Fallback: construct from BOOK_ID if Styles array is missing
        main_css = f"{BOOK_ID}.css"

    css_source = MEDIA_DIR / main_css
    css_target = oebps_css_dir / EPUB_CSS_NAME

    if css_source.exists():
        shutil.copy2(css_source, css_target)
        print(f"  Copied {main_css} -> {EPUB_CSS_NAME}")

        # Prepend a reference comment so we can trace the origin of styles.css
        try:
            with open(css_target, "r", encoding="utf-8") as f:
                original_css = f.read()
            with open(css_target, "w", encoding="utf-8") as f:
                header_comment = f"/* Source CSS: {main_css} | Book ID: {BOOK_ID} */\n"
                f.write(header_comment + original_css)
        except OSError as e:
            print(f"  Warning: Unable to annotate {EPUB_CSS_NAME} with source comment: {e}")
    else:
        print(f"  Warning: CSS file {main_css} not found in media/")

    # 2️⃣ Copy optional custom CSS (custom.css) for project-specific overrides
    if CUSTOM_CSS_FILE.exists():
        shutil.copy2(CUSTOM_CSS_FILE, oebps_css_dir / CUSTOM_CSS_FILE.name)
        print(f"  Copied {CUSTOM_CSS_FILE.name}")

        

def create_epub_zip():
    """Create the EPUB file (ZIP archive)"""
    print("Creating EPUB ZIP file...")
    
    # Place the final EPUB next to the generated EPUB folder (under the output root)
    epub_path = EPUB_DIR.parent / EPUB_NAME
    
    # Remove existing EPUB if it exists
    if epub_path.exists():
        epub_path.unlink()
    
    with zipfile.ZipFile(epub_path, 'w', zipfile.ZIP_DEFLATED) as epub_zip:
        # Add mimetype first (must be uncompressed)
        mimetype_path = EPUB_DIR / "mimetype"
        epub_zip.write(mimetype_path, "mimetype", compress_type=zipfile.ZIP_STORED)
        
        # Add all other files
        for root, dirs, files in os.walk(EPUB_DIR):
            # Skip mimetype as it's already added
            if 'mimetype' in files:
                files.remove('mimetype')
            
            for file in files:
                file_path = Path(root) / file
                # Get relative path from EPUB_DIR
                arcname = file_path.relative_to(EPUB_DIR)
                epub_zip.write(file_path, arcname)
    
    print(f"EPUB created: {epub_path}")
    return epub_path

def main():
    """Main function"""
    print("=" * 60)
    print("EPUB Generator")
    print("=" * 60)

    # Parse command-line arguments
    args = parse_args()

    # Resolve input directory (parallel to this script by default)
    input_dir_path = Path(args.input_dir)
    if not input_dir_path.is_absolute():
        input_dir_path = SOURCE_DIR / input_dir_path

    if not input_dir_path.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir_path}")

    # The JS file is expected to sit directly inside the input directory with the same base name
    js_file = input_dir_path / f"{input_dir_path.name}.js"
    if not js_file.exists():
        raise FileNotFoundError(f"JS content file not found in input directory: {js_file}")

    # Parse JS file
    data = parse_js_file(js_file)

    # Cache the original cover image file name (if any) for later use when
    # normalising image paths and building the manifest.
    global COVER_SOURCE_NAME
    cover_image_info = data.get('CoverImage', {}).get('media_info', {})
    cover_src = cover_image_info.get('src')
    COVER_SOURCE_NAME = os.path.basename(cover_src) if cover_src else None

    # Derive basic metadata with the following precedence:
    #   CLI args > JSON metadata (if available) > defaults
    book_title, book_id, book_author = extract_metadata_from_json(
        data,
        DEFAULT_BOOK_TITLE,
        DEFAULT_BOOK_ID,
        DEFAULT_BOOK_AUTHOR,
    )

    if args.title:
        book_title = args.title
    if args.book_id:
        book_id = args.book_id
    if args.author:
        book_author = args.author

    # Resolve output root (Final_ePUB by default)
    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = SOURCE_DIR / output_root

    # Initialise global configuration based on the chosen input folder and metadata
    init_config(input_dir_path, book_title, book_id, book_author, output_root)

    # Create EPUB structure
    oebps_dir, metainf_dir, oebps_media_dir, oebps_fonts_dir, oebps_xhtml_dir, oebps_css_dir = create_epub_structure()

    # Get TOC entries
    toc_entries = data.get('Toc', {})
    pages = data.get('Pages', {})
    
    # Generate HTML files
    print("Generating HTML files...")
    # Inside the EPUB, the main stylesheet is always named EPUB_CSS_NAME (e.g. styles.css)
    css_file = EPUB_CSS_NAME
    
    # Sort TOC entries by playOrder to assign page numbers
    sorted_toc = sorted(toc_entries.items(), key=lambda x: int(x[1].get('playOrder', 999)))
    page_number = 1
    
    for page_id, toc_entry in sorted_toc:
        if page_id in pages:
            page_data = pages[page_id]
            # Only assign page numbers to linear pages
            current_page_num = page_number if toc_entry.get('linear') == 'yes' else None
            html_content = generate_html_page(page_id, page_data, toc_entry, css_file, current_page_num)
            
            # Get filename from TOC href
            href = toc_entry.get('href', f'{page_id}.htm')
            html_filename = href.replace(BOOK_PREFIX, '').replace('.htm', '.xhtml')
            # Map front matter file names to match POC_ePUB: cvi -> cover, tp -> titlepage, crt -> copyright
            if html_filename == 'cvi.xhtml':
                html_filename = 'cover.xhtml'
            elif html_filename == 'tp.xhtml':
                html_filename = 'titlepage.xhtml'
            elif html_filename == 'crt.xhtml':
                html_filename = 'copyright.xhtml'
            html_path = oebps_xhtml_dir / html_filename
            
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            print(f"  Generated {html_filename}")
            if current_page_num is not None:
                page_number += 1
    
    # Create EPUB metadata files
    print("Creating EPUB metadata files...")
    create_mimetype()
    create_container_xml(metainf_dir)
    create_content_opf(data, toc_entries, oebps_dir)
    create_toc_ncx(data, toc_entries, oebps_dir)
    create_nav_xhtml(data, toc_entries, oebps_xhtml_dir, css_file)
    create_content_xhtml(data, toc_entries, oebps_xhtml_dir, css_file)
    
    # Copy audio files if they exist (for glossary with audio support)
    audio_source_dir = INPUT_DIR / "audio"
    if audio_source_dir.exists():
        audio_target_dir = OEBPS_DIR / "audio"
        audio_target_dir.mkdir(parents=True, exist_ok=True)
        print("Copying audio files...")
        for audio_file in audio_source_dir.glob('*.mp3'):
            shutil.copy2(audio_file, audio_target_dir / audio_file.name)
            print(f"  Copied {audio_file.name} to audio/")
    
    # Copy media, fonts, and CSS
    copy_media_files(oebps_media_dir, data)
    copy_font_files(oebps_fonts_dir)
    copy_css_file(data, oebps_css_dir)
    
    # Create EPUB ZIP
    epub_path = create_epub_zip()
    
    print("=" * 60)
    print(f"SUCCESS! EPUB created at: {epub_path}")
    print(f"EPUB structure available at: {EPUB_DIR}")
    print("=" * 60)

if __name__ == "__main__":
    main()
