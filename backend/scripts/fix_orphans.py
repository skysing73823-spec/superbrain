import os
import shutil
import datetime
from pathlib import Path

VAULT_DIR = r"E:\OneDrive\文件\ObsidianVault"
BACKUP_DIR = os.path.join(VAULT_DIR, "99-Archive", f"backup_phase2_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}")

def backup_file(filepath):
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    rel_path = os.path.relpath(filepath, VAULT_DIR)
    dest_path = os.path.join(BACKUP_DIR, rel_path)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    shutil.copy2(filepath, dest_path)
    return dest_path

# Known index files
INDEX_FILES = {
    "滑雪": os.path.join(VAULT_DIR, "滑雪市場研究.md"),
    "自動化": os.path.join(VAULT_DIR, "06-自動化.md"),
    "專案": os.path.join(VAULT_DIR, "10-Projects.md"),
    "相片": os.path.join(VAULT_DIR, "01-生活.md"), # assuming 05 is empty or we use a general one. Let's check if 05 exists
    "Inbox": os.path.join(VAULT_DIR, "00-Inbox.md")
}
if os.path.exists(os.path.join(VAULT_DIR, "05-相片影片.md")):
    INDEX_FILES["相片"] = os.path.join(VAULT_DIR, "05-相片影片.md")

# Hardcoded high-confidence resolutions based on filenames and locations
RESOLUTIONS = [
    {
        "orphan": os.path.join(VAULT_DIR, r"10-Projects\滑雪市場研究\schools\Evergreen.md"),
        "index": INDEX_FILES["滑雪"],
        "reason": "Located in 滑雪市場研究/schools folder, highly relevant to ski market.",
        "score": 0.95
    },
    {
        "orphan": os.path.join(VAULT_DIR, r"10-Projects\滑雪市場研究\schools\GoSnow.md"),
        "index": INDEX_FILES["滑雪"],
        "reason": "Located in 滑雪市場研究/schools folder, highly relevant to ski market.",
        "score": 0.95
    },
    {
        "orphan": os.path.join(VAULT_DIR, r"06-自動化\Syncthing 同步設定.md"),
        "index": INDEX_FILES["自動化"],
        "reason": "Syncthing is an automation/sync tool, located in 06-自動化.",
        "score": 0.92
    },
    {
        "orphan": os.path.join(VAULT_DIR, r"00-Inbox\拍攝備忘錄.md"),
        "index": INDEX_FILES.get("相片", INDEX_FILES["Inbox"]),
        "reason": "Relates to video/photo shooting (拍攝), fits into media or general index.",
        "score": 0.88
    },
    {
        "orphan": os.path.join(VAULT_DIR, r"Interests\Auto\openai.md"),
        "index": INDEX_FILES["自動化"],
        "reason": "OpenAI is heavily used in the automation backend.",
        "score": 0.85
    },
    {
        "orphan": os.path.join(VAULT_DIR, r"Interests\Auto\superbrain.md"),
        "index": INDEX_FILES["專案"],
        "reason": "Superbrain is a core project.",
        "score": 0.88
    },
    {
        "orphan": os.path.join(VAULT_DIR, r"10-Projects\SKI-AI\09_AI概念對照表.md"),
        "index": INDEX_FILES["專案"],
        "reason": "Part of the SKI-AI project docs.",
        "score": 0.90
    }
]

def append_link_to_index(index_path, orphan_path):
    orphan_name = Path(orphan_path).stem
    link = f"[[{orphan_name}]]"
    
    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    if link in content:
        return False # Already exists
        
    if "## 相關孤立筆記" not in content:
        content += "\n\n## 相關孤立筆記\n"
        
    content += f"- {link}\n"
    
    backup_file(index_path)
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(content)
    return True

def run():
    log_path = os.path.join(VAULT_DIR, "Orphan-Resolution-Log.md")
    linked_count = 0
    with open(log_path, "w", encoding="utf-8") as log:
        log.write("# 孤立筆記處理紀錄\n\n")
        log.write("| 孤立筆記 | 修改索引檔案 | 關聯理由 | 信心分數 |\n")
        log.write("| -------- | -------- | -------- | -------- |\n")
        
        for res in RESOLUTIONS:
            if not os.path.exists(res["orphan"]):
                continue
            if not os.path.exists(res["index"]):
                # Create the index if it doesn't exist
                os.makedirs(os.path.dirname(res["index"]), exist_ok=True)
                with open(res["index"], "w", encoding="utf-8") as f:
                    f.write(f"# {Path(res['index']).stem}\n")
            
            success = append_link_to_index(res["index"], res["orphan"])
            if success:
                linked_count += 1
                orphan_name = Path(res["orphan"]).stem
                index_name = Path(res["index"]).stem
                log.write(f"| [[{orphan_name}]] | [[{index_name}]] | {res['reason']} | {res['score']} |\n")
                
    print(f"Successfully linked {linked_count} orphans. Log saved to {log_path}")
    
if __name__ == "__main__":
    run()
