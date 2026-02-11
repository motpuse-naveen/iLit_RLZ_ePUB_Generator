# EPUB Generator

Generates EPUB files from a JS content file and associated media.

## Requirements (other machine)

1. **Python 3.6+**  
   The script uses only the standard library (no pip packages). Ensure Python 3 is installed:
   ```bash
   python3 --version
   ```

2. **Same project layout**  
   Copy (or recreate) this structure:
   - `generate_epub.py` – this script
   - `custom.css` – optional; used if present
   - **Input folder** – a directory that contains:
     - `{folder_name}.js` – JS file with `content = { ... }` (e.g. `b33dd8090ad64e9483f7ad08df480862.js`)
     - `media/` – images and `{BookId}.css`
     - `fonts/` – optional `.ttf` files
     - `audio/` – optional `.mp3` for glossary

   Example default input folder: `b33dd8090ad64e9483f7ad08df480862/`

## How to run

From the directory that contains `generate_epub.py`:

```bash
# Use default input folder (e.g. b33dd8090ad64e9483f7ad08df480862) and write to Final_ePUB/
python3 generate_epub.py

# Specify input folder
python3 generate_epub.py path/to/input_folder

# Override metadata and output location
python3 generate_epub.py path/to/input_folder --output-root ./My_Output --title "My Book" --book-id "1234567890" --author "Author Name"
```

Output: a folder under the output root (e.g. `Final_ePUB/BookTitle/`) and an `.epub` file (e.g. `Final_ePUB/BookTitle.epub`).

## Summary

| Need on other machine | Details |
|------------------------|--------|
| **Python** | 3.6 or newer (`python3` in PATH) |
| **Extra packages** | None (stdlib only) |
| **Files to copy** | Script + `custom.css` (optional) + input folder with `.js`, `media/`, and optional `fonts/`, `audio/` |
