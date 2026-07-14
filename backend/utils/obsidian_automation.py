import os
import sys
import shutil
import locale
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

import builtins
original_open = builtins.open

def utf8_open(file, mode='r', buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None):
    if 'b' not in mode and encoding is None:
        encoding = 'utf-8'
    return original_open(file, mode, buffering, encoding, errors, newline, closefd, opener)

builtins.open = utf8_open

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Ensure model router can be imported
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _load_openai_key() -> str:
    """Load OPENAI_API_KEY from environment or .api_keys file."""
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    api_keys_file = BACKEND_ROOT / "config" / ".api_keys"
    if api_keys_file.exists():
        for line in api_keys_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def _openai_generate(prompt: str) -> str:
    """Direct OpenAI Chat Completions call — used as fallback when model_router fails."""
    import json
    from urllib.request import Request, urlopen
    
    api_key = _load_openai_key()
    if not api_key:
        raise RuntimeError("No OPENAI_API_KEY found in environment or config/.api_keys")
    
    body = json.dumps({
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": 2000,
        "temperature": 0.4,
    }).encode("utf-8")
    
    req = Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


def generate_text(prompt: str) -> str:
    """Generate text: try model_router first, fall back to direct OpenAI."""
    # Try model_router (may have Groq, Gemini, OpenRouter, etc.)
    try:
        from core.model_router import get_router
        router = get_router()
        return router.generate_text(prompt)
    except Exception as e:
        print(f"  [Info] Model router unavailable ({type(e).__name__}: {e}), falling back to OpenAI direct.")
    
    # Fallback: direct OpenAI
    return _openai_generate(prompt)

def safe_write_with_backup(target_path: Path, content: str, vault_path: Path) -> None:
    """Write content to target_path. If target_path exists, backup it first to 99-Archive."""
    if target_path.exists():
        archive_dir = vault_path / "99-Archive" / "automation_backups"
        archive_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        safe_name = f"{target_path.stem}_backup_{timestamp}{target_path.suffix}"
        backup_path = archive_dir / safe_name
        shutil.copy2(target_path, backup_path)
    
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")

def get_existing_vault_notes(vault_path: Path) -> List[str]:
    """Scan vault and return a list of existant markdown note names, excluding noisy folders."""
    notes = []
    ignored_folders = {
        ".obsidian", ".claude", ".stversions", ".stfolder", 
        "Daily", "Timeline", "Media_Index", "99-Archive", 
        "Suggested-Links", "Weekly-Synthesis", "00-Inbox"
    }
    for root, dirs, files in os.walk(vault_path):
        # In-place modify dirs to skip ignored folders recursively
        dirs[:] = [d for d in dirs if d not in ignored_folders]
        for file in files:
            if file.endswith(".md"):
                full_path = Path(root) / file
                rel_path = full_path.relative_to(vault_path)
                notes.append(rel_path.as_posix())
    return notes

def load_recent_7_days_context(vault_path: Path, target_date_str: str) -> str:
    """Load Daily notes text from target_date_str going back 7 days."""
    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    date_strs = [(target_dt - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    context_text = ""
    for d in reversed(date_strs):
        daily_path = vault_path / "Daily" / f"{d}.md"
        if daily_path.exists():
            context_text += f"\n\n--- [[Daily/{d}]] ---\n"
            context_text += daily_path.read_text(encoding="utf-8", errors="ignore")
    return context_text.strip()

def update_current_context(vault_path: Path, target_date_str: str) -> str:
    """Aggregate recent 7 days notes and build/update CURRENT_CONTEXT.md using AI."""
    print("[Context] Updating CURRENT_CONTEXT.md...")
    recent_context = load_recent_7_days_context(vault_path, target_date_str)
    if not recent_context:
        print("  [Warning] No recent Daily notes found to generate context.")
        return ""
    
    prompt = f"""你是一個 Obsidian 知識庫整理助手。
請根據以下最近 7 天的 Daily notes 內容，整理並更新 `CURRENT_CONTEXT.md` 筆記。

【輸入內容】
{recent_context}

【輸出格式要求】
請以繁體中文輸出，並嚴格遵循以下 Markdown 結構。
注意：每項提取出來的項目必須附加來源連結如 `[[Daily/YYYY-MM-DD]]`。
不可將 AI 推測或待辦事項寫成「我已決定的決定」。如果某個部分沒有明確的證據支持，請寫「未記錄」，不可自行虛構。

# CURRENT CONTEXT

## 目前最高目標
- (從筆記內容中提取，若無明確證據則寫「未記錄」) [[來源連結]]

## 進行中專案
- (列出進行中的專案，附上內部連結如 [[專案名稱]]) [[來源連結]]

## 最近7天的重要決定
- (列出明確的重要決定。不可將 AI 的推測或待辦事項寫成決定！若無明確決定則寫「未記錄」) [[來源連結]]

## 尚未完成事項
- (列出尚未完成的待辦事項) [[來源連結]]

## 最近完成事項與證據等級
- (列出最近完成的事項。必須包含證據等級 L0~L4，例如：
  - [x] 完成某某排程修復 [[Daily/2026-07-15]] (證據等級: L4 - 完整修復、驗證、提交並推送，提供完整 Rollback 還原方案)
  
  證據分級標準說明：
  L0: 本地程式碼測試通過或正常產生輸出記錄。
  L1: 初步部署到預備或正式環境，功能可調用。
  L2: 在正式環境完成實體測試且返回預期數據。
  L3: 經過連續執行測試或兩次重試無衝突。
  L4: 完整修復、驗證、提交並推送，提供完整 Rollback 還原方案。)
"""
    content = generate_text(prompt)
    
    target_path = vault_path / "CURRENT_CONTEXT.md"
    safe_write_with_backup(target_path, content, vault_path)
    print("  [OK] CURRENT_CONTEXT.md updated.")
    return content

def generate_weekly_synthesis(vault_path: Path, target_date_str: str) -> str:
    """Generate Weekly-Synthesis note YYYY-Www.md using AI."""
    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    year, week, _ = target_dt.isocalendar()
    week_str = f"{year}-W{week:02d}"
    print(f"[Synthesis] Generating Weekly Synthesis for {week_str}...")
    
    recent_context = load_recent_7_days_context(vault_path, target_date_str)
    if not recent_context:
        print("  [Warning] No recent Daily notes found to generate Weekly Synthesis.")
        return ""
    
    prompt = f"""請根據以下最近 7 天的 Daily notes 內容，生成 `Weekly-Synthesis` 報告。

週別：{week_str}
輸入內容：
{recent_context}

【輸出格式要求】
請以繁體中文輸出，並嚴格遵循以下 Markdown 結構。
注意：每項提取出來的項目必須附加來源連結如 `[[Daily/YYYY-MM-DD]]`。
財務/營收等統計欄位若無任何明確記載，請一律寫「未記錄」，絕不可自行編造數值或進行盲目猜測。

# Weekly Synthesis {week_str}

## 本週完成事項
- (整理本週完成的事項) [[來源連結]]

## 重複主題
- (本週筆記中頻繁被提及或關注的主題或關鍵字) [[來源連結]]

## 相互矛盾的想法
- (列出本週筆記中是否有相互矛盾、猶豫不決或轉折的想法。若無則寫「未記錄」) [[來源連結]]

## 尚未完成的承諾
- (本週有承諾但尚未完成的事項) [[來源連結]]

## 營收與財務狀況
- 發文數：(若筆記有記載則寫數值，否則寫「未記錄」)
- 新詢問數：(同上)
- 成交／訂金：(同上)
- 營收：(同上)
- 現金水位：(同上)

## 下週最重要三件事
- 1. (提取下週計畫中最核心的三件事)
- 2. 
- 3.
"""
    content = generate_text(prompt)
    
    target_path = vault_path / "Weekly-Synthesis" / f"{week_str}.md"
    safe_write_with_backup(target_path, content, vault_path)
    print(f"  [OK] Weekly-Synthesis/{week_str}.md generated.")
    return content

def generate_suggested_links(vault_path: Path, target_date_str: str) -> str:
    """Recommend links between the today's Daily note and existing notes, avoiding hallucinations."""
    print(f"[Links] Generating Suggested-Links for {target_date_str}...")
    daily_path = vault_path / "Daily" / f"{target_date_str}.md"
    if not daily_path.exists():
        print(f"  [Warning] Daily note for {target_date_str} does not exist. Skipping links.")
        return ""
    
    today_content = daily_path.read_text(encoding="utf-8", errors="ignore")
    existing_notes = get_existing_vault_notes(vault_path)
    
    if not existing_notes:
        print("  [Warning] No existing notes found to link.")
        return ""
        
    prompt = f"""你是一個筆記關聯推薦系統。
今天新增了以下 Daily Note 內容：
---
{today_content}
---

在知識庫中，目前確實存在以下舊筆記檔案清單：
{chr(10).join('- ' + n for n in existing_notes)}

請分析今天的 Daily Note，從「目前確實存在」的舊筆記檔案中，推薦 1 到 3 篇最相關的筆記。

【輸出格式要求】
請以繁體中文輸出，格式如下：
# Suggested Links {target_date_str}

## 推薦關聯
- [[舊筆記名稱]]
  - **推薦理由**：(說明為什麼這篇舊筆記與今天的 Daily Note 相關)
  - **信心分數**：(0.0 到 1.0 的分數)

【注意】
1. 只能推薦現有清單中確實存在的筆記，絕不可虛構不存在的筆記連結！
2. 如果沒有適合推薦的，請寫「無適合推薦的關聯」。
"""
    content = generate_text(prompt)
    
    target_path = vault_path / "Suggested-Links" / f"{target_date_str}.md"
    safe_write_with_backup(target_path, content, vault_path)
    print(f"  [OK] Suggested-Links/{target_date_str}.md generated.")
    return content

def process_inbox(vault_path: Path) -> None:
    """Process files in 00-Inbox/raw/ into 00-Inbox/processed/, never overwriting raw files."""
    raw_dir = vault_path / "00-Inbox" / "raw"
    processed_dir = vault_path / "00-Inbox" / "processed"
    
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    
    raw_files = list(raw_dir.glob("*.md"))
    if not raw_files:
        print("[Inbox] Inbox/raw is empty. No incoming notes to process.")
        return
        
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    for rf in raw_files:
        pf = processed_dir / rf.name
        # Process only if processed file doesn't exist, or raw file is newer
        if not pf.exists() or rf.stat().st_mtime > pf.stat().st_mtime:
            print(f"[Inbox] Processing Inbox raw note: {rf.name}...")
            raw_content = rf.read_text(encoding="utf-8", errors="ignore")
            
            prompt = f"""你是一個知識整理助手。請幫我對以下隨手記下的 raw 筆記進行格式優化、去蕪存菁與分類整理，使其更具結構性，以利後續知識歸檔。
            
【原始內容】
{raw_content}

請輸出格式良好、清晰的 Markdown 整理版（使用繁體中文）。
"""
            processed_content = generate_text(prompt)
            
            header = f"原始檔案: [[00-Inbox/raw/{rf.name}]]\n處理時間: {now_str}\n\n---\n\n"
            full_processed_text = header + processed_content
            
            # Write with backup if processed file already exists
            safe_write_with_backup(pf, full_processed_text, vault_path)
            print(f"  [OK] Processed note written to 00-Inbox/processed/{rf.name}")

def run_automation(target_date_str: str, vault_path_str: str) -> Dict[str, Any]:
    """Main entry point for running the Obsidian Context and AI automation steps."""
    vault_path = Path(vault_path_str)
    
    # 建立必要的資料夾
    (vault_path / "00-Inbox" / "raw").mkdir(parents=True, exist_ok=True)
    (vault_path / "00-Inbox" / "processed").mkdir(parents=True, exist_ok=True)
    (vault_path / "Weekly-Synthesis").mkdir(parents=True, exist_ok=True)
    (vault_path / "Suggested-Links").mkdir(parents=True, exist_ok=True)
    
    results = {}
    try:
        # Step 1: Update CURRENT_CONTEXT.md
        cc_content = update_current_context(vault_path, target_date_str)
        results["current_context"] = len(cc_content) > 0
        
        # Step 2: Generate Suggested-Links
        sl_content = generate_suggested_links(vault_path, target_date_str)
        results["suggested_links"] = len(sl_content) > 0
        
        # Step 3: Generate Weekly Synthesis
        ws_content = generate_weekly_synthesis(vault_path, target_date_str)
        results["weekly_synthesis"] = len(ws_content) > 0
        
        # Step 4: Process Inbox
        process_inbox(vault_path)
        results["inbox_processed"] = True
        
        results["success"] = True
    except Exception as e:
        results["success"] = False
        results["error"] = str(e)
        import traceback
        traceback.print_exc()
        print(f"[Error] Error during Obsidian automation: {e}")
        
    return results

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--vault", default=r"E:\OneDrive\文件\ObsidianVault")
    args = parser.parse_args()
    
    res = run_automation(args.date, args.vault)
    print("Automation execution result:", res)
