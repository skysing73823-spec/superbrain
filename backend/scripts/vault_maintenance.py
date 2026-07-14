import os
import re
import shutil
import datetime
from pathlib import Path

VAULT_DIR = r"E:\OneDrive\文件\ObsidianVault"
BACKUP_DIR = os.path.join(VAULT_DIR, "99-Archive", f"backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}")

EXCLUDE_DIRS = [
    "Daily", "Timeline", "Media_Index", "Weekly-Synthesis", 
    "Suggested-Links", "90-Templates", "99-Archive", 
    ".obsidian", ".stversions", ".claude", "00-Inbox/raw"
]

def is_excluded(path_str):
    normalized = path_str.replace('\\', '/')
    for ex in EXCLUDE_DIRS:
        if f"/{ex}/" in normalized or normalized.endswith(f"/{ex}") or normalized.startswith(f"{EXCLUDE_DIRS[0][:0]}{ex}/"): # rudimentary check
            return True
        # better check:
        parts = Path(path_str).parts
        if ex in parts or (ex == "00-Inbox/raw" and "00-Inbox" in parts and "raw" in parts):
            return True
    return False

def get_all_md_files():
    files = []
    for root, _, filenames in os.walk(VAULT_DIR):
        if is_excluded(root):
            continue
        for f in filenames:
            if f.endswith(".md"):
                files.append(os.path.join(root, f))
    return files

def build_file_map(files):
    # Map basename (no ext) to absolute path
    # Also map lowercase basename to absolute path
    file_map = {}
    lower_map = {}
    for f in files:
        basename = Path(f).stem
        if basename not in file_map:
            file_map[basename] = []
        file_map[basename].append(f)
        
        l_basename = basename.lower()
        if l_basename not in lower_map:
            lower_map[l_basename] = []
        lower_map[l_basename].append(f)
        
    return file_map, lower_map

def find_links(content):
    # Regex for Obsidian links [[link]] or [[link|alias]] or [[link#header|alias]]
    pattern = r"\[\[(.*?)\]\]"
    return re.findall(pattern, content)

def backup_file(filepath):
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    rel_path = os.path.relpath(filepath, VAULT_DIR)
    dest_path = os.path.join(BACKUP_DIR, rel_path)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    shutil.copy2(filepath, dest_path)
    return dest_path

def fix_broken_links():
    files = get_all_md_files()
    file_map, lower_map = build_file_map(files)
    
    broken_links = []
    fixed_links = 0
    pending_links = []
    modified_files = set()
    
    # Pre-collect all valid link targets (by base name or relative path)
    
    for filepath in files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(filepath, 'r', encoding='cp950', errors='ignore') as f:
                content = f.read()
                
        links = find_links(content)
        new_content = content
        file_modified = False
        
        for link_inner in set(links):
            # Parse link
            target = link_inner.split('|')[0].split('#')[0]
            if not target:
                continue
                
            # Is it valid?
            # Obsidian resolves links by matching the base name anywhere in the vault.
            is_valid = False
            target_basename = Path(target).stem
            
            if target_basename in file_map:
                is_valid = True
            elif os.path.exists(os.path.join(VAULT_DIR, target)) or os.path.exists(os.path.join(VAULT_DIR, target + ".md")):
                is_valid = True
                
            if not is_valid:
                broken_links.append((filepath, link_inner))
                
                # Try to fix: case insensitive match
                target_lower = target_basename.lower()
                if target_lower in lower_map and len(lower_map[target_lower]) == 1:
                    # High confidence unique match (case difference)
                    correct_target = Path(lower_map[target_lower][0]).stem
                    # Replace in content (careful with regex)
                    old_str = f"[[{link_inner}]]"
                    # reconstruct with correct target but keeping alias/header if any
                    parts = link_inner.split('|')
                    if len(parts) > 1:
                        new_str = f"[[{correct_target}|{parts[1]}]]"
                    else:
                        header_parts = link_inner.split('#')
                        if len(header_parts) > 1:
                            new_str = f"[[{correct_target}#{header_parts[1]}]]"
                        else:
                            new_str = f"[[{correct_target}]]"
                    
                    new_content = new_content.replace(old_str, new_str)
                    file_modified = True
                    fixed_links += 1
                else:
                    pending_links.append((filepath, link_inner))
                    
        if file_modified:
            backup_file(filepath)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            modified_files.add(filepath)

    return len(files), len(broken_links), fixed_links, pending_links, len(modified_files)

def find_orphans():
    files = get_all_md_files()
    file_map, lower_map = build_file_map(files)
    
    incoming_links = {f: 0 for f in files}
    
    for filepath in files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except:
            continue
        
        links = find_links(content)
        for link_inner in set(links):
            target = link_inner.split('|')[0].split('#')[0]
            target_basename = Path(target).stem
            if target_basename in file_map:
                for target_file in file_map[target_basename]:
                    incoming_links[target_file] += 1
                    
    orphans = [f for f, count in incoming_links.items() if count == 0]
    return orphans

if __name__ == "__main__":
    total_files, total_broken, fixed, pending, modified_count = fix_broken_links()
    orphans = find_orphans()
    
    print(f"Total Markdown Files: {total_files}")
    print(f"Total Broken Links Found: {total_broken}")
    print(f"Fixed Links: {fixed}")
    print(f"Pending Broken Links: {len(pending)}")
    print(f"Modified Files for Fixes: {modified_count}")
    print(f"Total Orphaned Notes: {len(orphans)}")
    
    # Save pending to report
    report_path = os.path.join(VAULT_DIR, "Pending-Broken-Links-Report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Pending Broken Links\n\n")
        for filepath, link in pending:
            f.write(f"- File: [[{Path(filepath).stem}]] -> Broken Link: [[{link}]]\n")
    print(f"Pending links report saved to {report_path}")
    
    orphan_report = os.path.join(VAULT_DIR, "Orphaned-Notes.md")
    with open(orphan_report, "w", encoding="utf-8") as f:
        f.write("# Orphaned Notes\n\n")
        for o in orphans:
            f.write(f"- [[{Path(o).stem}]]\n")
