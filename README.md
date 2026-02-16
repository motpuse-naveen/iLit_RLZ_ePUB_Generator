# EPUB Generator

A Python script that generates EPUB 3.3 files from JavaScript content files and associated media assets.

## Overview

This tool converts structured JavaScript content files (containing book data, pages, and metadata) into fully compliant EPUB 3.3 files. It automatically extracts metadata from the content, processes HTML pages, manages assets (images, fonts, CSS), and creates a properly structured EPUB package.

## Requirements

### System Requirements

- **Python 3.6+**  
  The script uses only the Python standard library (no external packages required). Verify your Python installation:
  ```bash
  python3 --version
  ```

### Project Structure

Copy (or recreate) the following structure:

```
project_root/
├── generate_epub.py          # Main script
├── custom.css                # Optional: Project-specific CSS overrides
└── {input_folder}/           # Input directory (e.g., default_input_dir/)
    ├── {folder_name}.js      # JS file with content = { ... }
    ├── media/                # Required: Images and CSS files
    │   ├── {BookId}.css      # Main stylesheet
    │   └── *.jpg             # Image assets
    ├── fonts/                # Optional: Font files (.ttf)
    └── audio/                # Optional: Audio files (.mp3) for glossary
```

**Example:** Default input folder: `default_input_dir/`

### IXE (Ingest XML Exchange)

IXE is an XML format produced by converting the same JSON content (from the `.js` file) into schema-valid XML for downstream use (e.g. Aptara). See:

- **Schema:** [`schema/ixe.xsd`](schema/ixe.xsd) — XSD definition (namespace `http://savvas.com/ixe/1.0`).
- **Documentation:** [`docs/IXE.md`](docs/IXE.md) — element mapping rules (JSON → IXE) and metadata expectations.

To **create IXE XML** from an input folder or `.js` file:

```bash
python3 json_to_ixe.py path/to/input_folder              # writes {folder_name}.ixe.xml
python3 json_to_ixe.py path/to/file.js -o output.ixe.xml # custom output path
```

## Quick Start

### Basic Usage

```bash
# Use default input folder and output to Final_ePUB/
python3 generate_epub.py

# Specify custom input folder
python3 generate_epub.py path/to/input_folder

# Override metadata and output location
python3 generate_epub.py path/to/input_folder \
    --output-root ./My_Output \
    --title "My Book Title" \
    --book-id "1234567890" \
    --author "Author Name"
```

### Output

The script generates:
- **EPUB folder**: `{output_root}/{BookTitle}_{BookID}/` (e.g., `Final_ePUB/CRASH_DIVE_0822452596/`)
- **EPUB file**: `{output_root}/{BookTitle}_{BookID}.epub` (e.g., `Final_ePUB/CRASH_DIVE_0822452596.epub`)

## Command-Line Parameters

### Positional Arguments

#### `input_dir` (optional)

- **Usage:** `python3 generate_epub.py [input_dir]`
- **Default:** `"default_input_dir"`
- **Description:** Input folder containing:
  - JS file (`{input_dir_name}.js`)
  - `media/` directory with images and CSS
  - Optional `fonts/` directory
  - Optional `audio/` directory
- **Example:**
  ```bash
  python3 generate_epub.py my_book_folder
  ```

### Optional Arguments

#### `--output-root`

- **Usage:** `--output-root <directory>`
- **Default:** `"Final_ePUB"`
- **Description:** Output root directory (can be absolute or relative to script location)
- **Example:**
  ```bash
  python3 generate_epub.py --output-root /path/to/output
  python3 generate_epub.py --output-root MyOutput
  ```

#### `--title`

- **Usage:** `--title "Book Title"`
- **Default:** Extracted from JSON (`Pages.tp` → `<h1 class='title'>`) or `"Book Title"`
- **Description:** Override book title
- **Example:**
  ```bash
  python3 generate_epub.py --title "My Book Title"
  ```

#### `--book-id`

- **Usage:** `--book-id "1234567890"`
- **Default:** Extracted from JSON (`BookId`/`BookID`/`ISBN` or `Styles` array) or `"Book_Id"`
- **Description:** Override book ID/ISBN
- **Example:**
  ```bash
  python3 generate_epub.py --book-id "0822452596"
  ```

#### `--author`

- **Usage:** `--author "Author Name"`
- **Default:** Extracted from JSON (`Pages.tp` → `<h1 class='author'>`) or `"Book Author"`
- **Description:** Override book author
- **Example:**
  ```bash
  python3 generate_epub.py --author "John Doe"
  ```

## Metadata Extraction Priority

The script extracts metadata in the following priority order (highest to lowest):

1. **CLI Arguments** (highest priority)
   - Values provided via command-line flags override all other sources

2. **JSON Metadata** (extracted from content)
   - **Title:** Extracted from `Pages.tp` → `<h1 class='title'>` HTML
   - **Author:** Extracted from `Pages.tp` → `<h1 class='author'>` HTML
   - **Book ID:** Extracted from top-level `BookId`/`BookID`/`ISBN` fields, or from `Styles` array (first CSS filename without extension)

3. **Default Values** (lowest priority)
   - Fallback values defined in the script

## Usage Examples

### Example 1: Basic Usage with Defaults

```bash
python3 generate_epub.py
```

Uses default input folder and extracts all metadata from JSON.

### Example 2: Custom Input Folder

```bash
python3 generate_epub.py my_book_folder
```

Processes content from `my_book_folder/` directory.

### Example 3: Override All Metadata

```bash
python3 generate_epub.py my_book_folder \
    --title "CRASH DIVE" \
    --book-id "0822452596" \
    --author "Lee Frederick"
```

### Example 4: Custom Output Directory

```bash
python3 generate_epub.py --output-root /path/to/output
```

### Example 5: Complete Example

```bash
python3 generate_epub.py default_input_dir \
    --output-root Final_ePUB \
    --title "CRASH DIVE" \
    --book-id "0822452596" \
    --author "Lee Frederick"
```

## Features

- **Automatic Metadata Extraction**: Extracts title, author, and book ID from JSON content
- **EPUB 3.3 Compliant**: Generates standards-compliant EPUB files
- **Asset Management**: Handles images, fonts, CSS, and audio files
- **Accessibility**: Includes proper ARIA attributes and semantic markup
- **Navigation**: Creates both EPUB 3.3 navigation document (`toc.xhtml`) and NCX file for backward compatibility
- **Custom Styling**: Supports project-specific CSS overrides via `custom.css`

## Summary

| Requirement | Details |
|------------|---------|
| **Python** | 3.6 or newer (`python3` in PATH) |
| **Extra Packages** | None (stdlib only) |
| **Files to Copy** | Script + `custom.css` (optional) + input folder with `.js`, `media/`, and optional `fonts/`, `audio/` |

## Notes

- The EPUB filename and folder name use the format: `{BookTitle}_{BookID}` (spaces in title are replaced with underscores)
- The script automatically handles file name mappings (e.g., `cvi` → `cover.xhtml`, `tp` → `titlepage.xhtml`)
- All HTML content is processed to ensure EPUB compliance and accessibility standards
