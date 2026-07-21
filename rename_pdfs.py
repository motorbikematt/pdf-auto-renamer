# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "pymupdf",
#     "pypdf",
# ]
# ///

import os
import re
import argparse
import glob
import csv
from datetime import datetime
import urllib.request
import urllib.parse
import json
import fitz  # PyMuPDF: Used for visual text extraction
from pypdf import PdfReader, PdfWriter  # pypdf: Used for metadata injection

def clean_filename(title):
    """Sanitizes the title for Windows filenames."""
    if not title:
        return "Unknown_Title"
    title = " ".join(title.split())
    title = title.replace(':', ' -')
    title = re.sub(r'[<>"/\\|\?\*]', '', title)
    return title[:150].strip()

def fetch_metadata_from_doi(text):
    """Attempts to find a DOI in text and queries CrossRef for official metadata."""
    doi_match = re.search(r'10\.\d{4,9}/[-._;()/:A-Za-z0-9]+', text)
    if not doi_match:
        return None
        
    doi = doi_match.group(0).rstrip('.-,;')
    
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}"
    req = urllib.request.Request(url, headers={'User-Agent': 'PDFAutoRenamer/1.0 (mailto:test@example.com)'})
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            msg = data.get('message', {})
            
            meta = {}
            title_list = msg.get('title', [])
            if title_list:
                meta['/Title'] = title_list[0]
                
            authors = msg.get('author', [])
            if authors:
                author_names = []
                for a in authors:
                    name = f"{a.get('given', '')} {a.get('family', '')}".strip()
                    if name:
                        author_names.append(name)
                if author_names:
                    meta['/Author'] = ", ".join(author_names)
                    
            journal = msg.get('container-title', [])
            if journal:
                meta['/Subject'] = journal[0]
                
            return meta if meta else None
            
    except Exception as e:
        print(f"      [!] DOI Lookup failed for {doi}: {e}")
    return None

def is_uninformative_metadata(title):
    """Evaluates if a metadata title is useless."""
    if not title or not title.strip():
        return True
        
    title_upper = title.strip().upper()
    bad_titles = ["LIPPINCOTT WILLIAMS AND WILKINS", "UNTITLED"]
    if title_upper in bad_titles:
        return True
        
    # Catch Elsevier PII (Publisher Item Identifier) strings which are just serial numbers
    if title_upper.startswith("PII:") or title_upper.startswith("PII -"):
        return True
        
    # Catch titles that are just DOIs
    if title_upper.startswith("DOI:") or ("10." in title and "/" in title and len(title.split()) == 1):
        return True
        
    return False

def is_likely_academic_paper(filepath):
    """Detects if a PDF is an academic paper by checking for common structural keywords."""
    try:
        doc = fitz.open(filepath)
        try:
            if len(doc) == 0:
                return False
                
            # Check text on the first two pages
            text = ""
            for i in range(min(2, len(doc))):
                text += doc[i].get_text("text").lower()
                
            academic_keywords = [
                "abstract", "doi:", "doi.org", "keywords:", "materials and methods",
                "introduction", "references", "published by", "university", "journal"
            ]
            
            # If we find at least one strong keyword, classify as academic
            for kw in academic_keywords:
                if kw in text:
                    return True
            return False
        finally:
            doc.close()
    except Exception:
        # Default to True so it proceeds normally if PyMuPDF throws a read error
        return True 

def extract_title_from_content(filepath):
    """Heuristic to extract title from the first page's largest font."""
    try:
        doc = fitz.open(filepath)
        try:
            if len(doc) == 0:
                return None
            page = doc[0] 
            blocks = page.get_text("dict")["blocks"]
            texts = []
            for b in blocks:
                if b.get('type') == 0: 
                    for line in b.get("lines", []):
                        for span in line.get("spans", []):
                            text = span.get("text", "").strip()
                            size = span.get("size", 0)
                            if text:
                                texts.append({"text": text, "size": size})
            if not texts:
                return None
            sizes = {}
            for t in texts:
                if len(t["text"]) > 2:
                    rounded_size = round(t["size"], 1)
                    sizes.setdefault(rounded_size, []).append(t["text"])
            if not sizes:
                return None
                
            sorted_sizes = sorted(sizes.items(), reverse=True)
            largest_size, largest_text_parts = sorted_sizes[0]
            largest_text = " ".join(largest_text_parts)
            
            # Edge Case: If the largest text is just the Journal name
            if "journal" in largest_text.lower() and len(sorted_sizes) > 1:
                second_largest_size, second_largest_text_parts = sorted_sizes[1]
                return " ".join(second_largest_text_parts)
                
            return largest_text
        finally:
            doc.close()
    except Exception as e:
        print(f"  [!] PyMuPDF Error reading {os.path.basename(filepath)}: {e}")
        return None

def get_or_create_log_file(folder):
    """Finds an existing log file or returns a new path with the current timestamp."""
    existing_logs = glob.glob(os.path.join(folder, "PDF_Title_Rename*.log"))
    if existing_logs:
        return existing_logs[0]
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(folder, f"PDF_Title_Rename{timestamp}.log")

def write_logs(log_file, new_logs):
    """Prepends new logs to the CSV file, keeping the header at the top."""
    if not new_logs:
        return
        
    existing_rows = []
    header = ["Timestamp", "Action", "Original_Filename", "New_Filename", "Status_Note"]
    
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8', newline='') as f:
            reader = csv.reader(f)
            try:
                first_row = next(reader)
                if first_row == header:
                    existing_rows = list(reader)
                else:
                    existing_rows = [first_row] + list(reader)
            except StopIteration:
                pass
                
    combined_rows = new_logs + existing_rows
    
    with open(log_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(combined_rows)

def echo_description(parser):
    print("-" * 65)
    print(" PDF Auto-Renamer Utility")
    print(" This script automatically renames academic PDFs based on their")
    print(" true titles, while safely preserving the original filenames in")
    print(" hidden metadata so the action can be reversed at any time.")
    print("-" * 65)
    print("")
    parser.print_help()
    print("-" * 65)
    print("")

def run_rename(folder, args, parser):
    echo_description(parser)
    
    target_files = []
    if args.files:
        print(f"Scanning {len(args.files)} explicitly requested file(s)...\n")
        target_files = [os.path.basename(f) for f in args.files]
    else:
        print("Scanning folder for PDFs...\n")
        target_files = os.listdir(folder)
    
    total_pdfs = 0
    already_processed = 0
    academic_files = []
    suspicious_files = []
    
    for filename in target_files:
        if not filename.lower().endswith('.pdf'):
            continue
            
        filepath = os.path.join(folder, filename)
        if not os.path.exists(filepath):
            print(f"  [!] File not found: {filename}")
            continue
            
        total_pdfs += 1
        
        try:
            reader = PdfReader(filepath)
            if reader.metadata and "/OriginalFileName" in reader.metadata:
                original_name = reader.metadata["/OriginalFileName"]
                if filename != original_name:
                    already_processed += 1
                    continue
        except Exception:
            pass
            
        if is_likely_academic_paper(filepath):
            academic_files.append(filename)
        else:
            suspicious_files.append(filename)
            
    to_process_total = len(academic_files) + len(suspicious_files)
    
    print(f"Total valid PDFs found: {total_pdfs}")
    print(f"Already processed (hidden metadata found): {already_processed}")
    print(f"Ready to process (academic): {len(academic_files)}")
    print(f"Suspicious files (likely not academic): {len(suspicious_files)}\n")
    
    if to_process_total == 0:
        if args.yes:
            print("No new files to process. Exiting (--yes flag is active).")
            return
            
        if already_processed > 0:
            resp = input("No new files to process. Would you like to restore files to their original names instead? (y/n): ")
            if resp.strip().lower() in ['y', 'yes']:
                print("")
                run_restore(folder, args, parser, skip_echo=True)
            else:
                print("Exiting.")
        else:
            print("No PDFs found to process or restore. Exiting.")
        return

    skip_suspicious = False
    if len(suspicious_files) > 0:
        print("-" * 40)
        print(" SUSPICIOUS FILES DETECTED ")
        print("-" * 40)
        for f in suspicious_files:
            print(f"  - {f}")
        print("-" * 40)
        print("These files do not appear to be standard academic papers. Visual")
        print("heuristics may produce unpredictable titles (e.g. mapping scales).")
        
        if not args.yes:
            resp = input("\nType 'SKIP' to exclude these files, or press Enter to process ALL files: ")
            if resp.strip().upper() == 'SKIP':
                skip_suspicious = True
                print("Suspicious files will be skipped.\n")
            else:
                print("Suspicious files WILL be processed.\n")
        else:
            print("Auto-confirm active: Suspicious files WILL be processed.\n")

    final_process_list = academic_files.copy()
    if not skip_suspicious:
        final_process_list.extend(suspicious_files)
        
    if len(final_process_list) == 0:
        print("No files left to process after skipping. Exiting.")
        return
        
    if not args.yes:
        resp = input(f"Proceed with processing {len(final_process_list)} files? (y/n): ")
        if resp.strip().lower() not in ['y', 'yes']:
            revert_resp = input("Aborting processing. Would you like to restore files to their original names instead? (y/n): ")
            if revert_resp.strip().lower() in ['y', 'yes']:
                print("")
                run_restore(folder, args, parser, skip_echo=True)
            else:
                print("Exiting.")
            return
    else:
        print(f"Auto-proceeding with {len(final_process_list)} files (--yes flag is active).")
        
    print("\nStarting Rename Process...")
    log_file = get_or_create_log_file(folder)
    run_logs = []
    
    for filename in final_process_list:
        filepath = os.path.join(folder, filename)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"Processing: {filename}")
        
        try:
            reader = PdfReader(filepath)
        except Exception as e:
            print(f"  [!] Could not read PDF properties: {e}")
            run_logs.append([timestamp, "ERROR", filename, "", f"Read error: {e}"])
            print("-" * 60)
            continue

        new_title = None
        fetched_metadata = None
        
        if not getattr(args, 'no_doi', False):
            print("  -> Attempting DOI lookup for official metadata...")
            try:
                doc = fitz.open(filepath)
                try:
                    text_for_doi = ""
                    for i in range(min(2, len(doc))):
                        text_for_doi += doc[i].get_text("text")
                finally:
                    doc.close()
                
                fetched_metadata = fetch_metadata_from_doi(text_for_doi)
                if fetched_metadata and '/Title' in fetched_metadata:
                    new_title = fetched_metadata['/Title']
                    print(f"  -> Found official metadata via CrossRef DOI: {new_title}")
                else:
                    print("  -> No valid DOI found or lookup failed. Falling back...")
            except Exception as e:
                print(f"  -> Error during DOI lookup: {e}")
                
        if not new_title:
            try:
                meta = reader.metadata
                meta_title = meta.title if meta else None
                if not is_uninformative_metadata(meta_title):
                    print(f"  -> Found valid embedded metadata title: {meta_title}")
                    new_title = meta_title
                else:
                    print("  -> Embedded metadata title missing or uninformative.")
            except Exception as e:
                print(f"  -> Error reading embedded metadata: {e}")

        if not new_title:
            new_title = extract_title_from_content(filepath)
            if new_title:
                print(f"  -> Found title from visual content (largest font): {new_title}")
            else:
                print("  -> [FAILED] Could not determine title.")
                run_logs.append([timestamp, "FAIL", filename, "", "No title found"])
                print("-" * 60)
                continue
                
        safe_title = clean_filename(new_title)
        new_filename = f"{safe_title}.pdf"
        new_filepath = os.path.join(folder, new_filename)
        
        if os.path.exists(new_filepath) and new_filename != filename:
            print(f"  [!] Cannot rename: A file named '{new_filename}' already exists.")
            run_logs.append([timestamp, "FAIL", filename, new_filename, "Target file exists"])
            print("-" * 60)
            continue
            
        if args.dry_run:
            print(f"  [DRY RUN] Would inject metadata and rename to: {new_filename}")
            run_logs.append([timestamp, "DRY-RUN RENAME", filename, new_filename, "Simulated Success"])
            print("-" * 60)
            continue
            
        temp_filepath = os.path.join(folder, f"temp_{filename}")
        try:
            writer = PdfWriter(clone_from=filepath)
            meta_dict = dict(reader.metadata) if reader.metadata else {}
            
            if fetched_metadata:
                meta_dict.update(fetched_metadata)
                
            meta_dict["/OriginalFileName"] = filename
            writer.add_metadata(meta_dict)
            
            with open(temp_filepath, "wb") as f:
                writer.write(f)
                
            if hasattr(writer, 'close'):
                writer.close()
                
            if filepath != new_filepath:
                os.rename(filepath, filepath + ".bak")
                os.rename(temp_filepath, new_filepath)
                os.remove(filepath + ".bak")
            else:
                os.replace(temp_filepath, new_filepath)
                
            print(f"  [SUCCESS] Injected metadata and renamed to: {new_filename}")
            run_logs.append([timestamp, "RENAME", filename, new_filename, "Success"])
            
        except Exception as e:
            print(f"  [!] Error during PDF rewriting: {e}")
            run_logs.append([timestamp, "ERROR", filename, new_filename, f"Rewrite error: {e}"])
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
            if os.path.exists(filepath + ".bak"):
                os.rename(filepath + ".bak", filepath)
                
        print("-" * 60)
        
    write_logs(log_file, run_logs)
    print("Process complete!")


def run_restore(folder, args, parser, skip_echo=False, suspicious_only=False):
    if not skip_echo:
        echo_description(parser)
        
    target_files = []
    if args.files:
        print(f"Scanning {len(args.files)} explicitly requested file(s) for restore...\n")
        target_files = [os.path.basename(f) for f in args.files]
    else:
        print("Scanning folder for PDFs to restore...\n")
        target_files = os.listdir(folder)
    
    total_pdfs = 0
    can_restore_files = []
    cannot_restore = 0
    
    for filename in target_files:
        if not filename.lower().endswith('.pdf'):
            continue
            
        filepath = os.path.join(folder, filename)
        if not os.path.exists(filepath):
            print(f"  [!] File not found: {filename}")
            continue
            
        total_pdfs += 1
        
        try:
            reader = PdfReader(filepath)
            if reader.metadata and "/OriginalFileName" in reader.metadata:
                if suspicious_only:
                    if not is_likely_academic_paper(filepath):
                        can_restore_files.append(filename)
                    else:
                        cannot_restore += 1
                else:
                    can_restore_files.append(filename)
            else:
                cannot_restore += 1
        except Exception:
            cannot_restore += 1
            
    can_restore = len(can_restore_files)
    
    if suspicious_only:
        print(f"Total valid PDFs checked: {total_pdfs}")
        print(f"Ready to restore (suspicious ONLY): {can_restore}")
        print(f"Skipping (academic or no metadata): {cannot_restore}\n")
    else:
        print(f"Total valid PDFs checked: {total_pdfs}")
        print(f"Ready to restore (hidden metadata found): {can_restore}")
        print(f"Cannot restore (no hidden metadata): {cannot_restore}\n")
    
    if can_restore == 0:
        print("No files can be restored. Exiting.")
        return
        
    if not args.yes:
        resp = input(f"Proceed with restoring {can_restore} files? (y/n): ")
        if resp.strip().lower() not in ['y', 'yes']:
            print("Aborting.")
            return
    else:
        print(f"Auto-proceeding with restoring {can_restore} files (--yes flag is active).")
        
    print("\nStarting Restore Process...")
    log_file = get_or_create_log_file(folder)
    run_logs = []
    
    for filename in can_restore_files:
        filepath = os.path.join(folder, filename)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            reader = PdfReader(filepath)
            meta = reader.metadata
            original_name = meta["/OriginalFileName"]
            
            if original_name == filename:
                print(f"[-] '{filename}' is already at its original name.")
                continue
                
            new_filepath = os.path.join(folder, original_name)
            
            if os.path.exists(new_filepath):
                print(f"[!] Cannot restore '{filename}': '{original_name}' already exists.")
                run_logs.append([timestamp, "FAIL", filename, original_name, "Target file exists"])
                continue
                
            if args.dry_run:
                print(f"[DRY RUN] Would restore '{filename}' -> '{original_name}'")
                run_logs.append([timestamp, "DRY-RUN RESTORE", filename, original_name, "Simulated Success"])
                continue
                
            os.rename(filepath, new_filepath)
            print(f"[SUCCESS] Restored '{filename}' -> '{original_name}'")
            run_logs.append([timestamp, "RESTORE", filename, original_name, "Success"])
            
        except Exception as e:
            print(f"[!] Error reading metadata for '{filename}': {e}")
            run_logs.append([timestamp, "ERROR", filename, "", f"Read error: {e}"])
            
    write_logs(log_file, run_logs)
    print("Process complete!")


def main():
    parser = argparse.ArgumentParser(
        description="PDF Auto-Renamer: Rename PDFs based on heuristics and inject original names into hidden metadata.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    # Optional positional arguments for passing specific files
    parser.add_argument("files", nargs="*", help="Optional specific PDF files to process. If omitted, processes all PDFs in the directory.")
    
    parser.add_argument("--restore", action="store_true", help="Restore files to their original names using hidden metadata.")
    parser.add_argument("--restore-suspicious", action="store_true", help="Restore ONLY files deemed suspicious (non-academic) to their original names.")
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-confirm all prompts. Runs without asking for permission.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate the process without modifying or moving any files on disk.")
    parser.add_argument("--no-doi", action="store_true", help="Disable the default CrossRef DOI lookup (useful if offline or rate-limited).")
    
    args = parser.parse_args()

    # Determine folder dynamically based on where the script is located
    folder = os.path.dirname(os.path.abspath(__file__))
    
    if args.restore_suspicious:
        run_restore(folder, args, parser, suspicious_only=True)
    elif args.restore:
        run_restore(folder, args, parser, suspicious_only=False)
    else:
        run_rename(folder, args, parser)

if __name__ == "__main__":
    main()
