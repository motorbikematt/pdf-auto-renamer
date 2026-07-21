# PDF Auto-Renamer

A robust Python utility that automatically renames academic PDFs based on their true titles, while safely preserving the original filenames in hidden metadata so the action can be reversed at any time. I made this script with Gemini CLI in response to Google NotebookLM unfortunate behavior of not being able to batch change the title of the sources to make it easier to navigate once uploaded.

You'd think if I can make this script, they could incorporate this feature default into their tools. Let me know if this helps you out ;)

Motorbikematt

## Requirements & Setup

This script uses [uv](https://github.com/astral-sh/uv) to manage dependencies dynamically via PEP 723 inline script metadata. 

There is no need to manually `pip install` dependencies or set up a virtual environment. As long as `uv` is installed on your system, it will seamlessly pull the required `pypdf` and `PyMuPDF` packages into a temporary environment at runtime.

## Features & Capabilities

- **Smart Title Extraction**: Scans standard embedded PDF metadata to find the real title of the paper.
- **Visual Heuristic Fallback**: If the metadata is missing or uninformative, it uses font-size heuristics (`PyMuPDF`) to extract the title directly from the largest text on the first page.
- **Academic Content Verification**: During the pre-scan phase, the script checks the first two pages of every PDF for standard academic keywords (e.g., `abstract`, `doi:`, `introduction`). Files lacking these markers are flagged as "Suspicious" (likely maps, brochures, or malformed docs) and separated from the main batch to prevent weird heuristic renaming.
- **Hidden Metadata Tracking**: Safely injects a custom, hidden `/OriginalFileName` key into the PDF's internal metadata before renaming. This leaves no duplicate files and preserves the original name indefinitely.
- **Interactive Safety Pre-Scan**: Runs a completely non-destructive pre-scan of your folder, outputs a breakdown of what files are ready to process vs. suspicious, and explicitly asks for your permission before modifying anything on disk.
- **Smart CSV Logging**: Maintains a single CSV log file (`PDF_Title_Rename[TIMESTAMP].log`). New actions are automatically prepended to the top of the file (just beneath the headers).
- **Idempotent / Fast Skipping**: The script automatically checks if a file has the hidden metadata. If it has already been processed, it is skipped quickly to save time and tersely logged.
- **Portable**: Uses relative paths, meaning you can drop the script into any folder on any drive and it will natively process the PDFs in that specific directory.


## Usage

Place the script (`rename_pdfs.py`) inside the directory containing the PDFs you want to process. 

### Basic Execution (Bulk Processing)
To run an interactive pre-scan and process all PDFs in the folder:
```powershell
uv run rename_pdfs.py
```

### Targeted Execution
You can selectively process one or more specific files by passing them as arguments:
```powershell
uv run rename_pdfs.py paper1.pdf paper2.pdf
```

### Restoring Original Filenames
Read the hidden metadata and cleanly revert all processed PDFs back to their exact original filenames:
```powershell
uv run rename_pdfs.py --restore
```
*(You can also pass specific filenames here to restore only those files).*

## CLI Flags

The script supports several flags to automate or tweak its behavior:

| Flag | Description |
| :--- | :--- |
| `--restore` | Restores files to their original names using the hidden metadata. |
| `--restore-suspicious` | Scans processed files, re-evaluates their text, and restores **ONLY** the files deemed suspicious (non-academic). Useful if you bulk-renamed files and later realize some non-academic documents were caught in the crossfire. |
| `--no-doi` | Disables the default CrossRef API lookup. If passed, the script will skip searching for a DOI and will rely entirely on the embedded metadata and visual heuristics (useful if you are offline or rate-limited). |
| `-y, --yes` | **Auto-Confirm:** Bypasses all interactive `(y/n)` prompts. The script will execute autonomously without halting for your permission. |
| `--dry-run` | **Simulation Mode:** Scans the files, evaluates the titles, and logs the planned actions to the console/CSV, but does **not** actually modify, rename, or move any files on your disk. |
