import os
import base64
import json
import requests
import shutil
import argparse
from pathlib import Path
from datetime import datetime

api_url = "https://ai.hackclub.com/proxy/v1/chat/completions"
api_key = "sk-hc-v1-92624fcb92464305a0461b27bd661b0514a787f5948f4938b3f7c077d9ea7fa7"

llm = "qwen/qwen3-32b"
vlm = "qwen/qwen3-vl-235b-a22b-instruct"

home = Path.home()
rules = home / ".smartsort_rules.json"
history = home / ".smartsort_history.json"

default = {
    "Images": ["jpg","jpeg","png","gif","webp","tiff","bmp","svg"],
    "Videos": ["mp4","mkv","mov","avi","webm","flv"],
    "Audio":  ["mp3","wav","flac","aac","ogg","m4a"],
    "Docs":   ["pdf","doc","docx","txt","md","odt","rtf"],
    "Code":   ["py","js","java","c","cpp","rs","go","rb","sh","html","css","json","yml","yaml","ts"],
    "Archives":["zip","tar","gz","bz2","7z","rar"],
    "Misc":   []
}

junk_pattern = ["thumbs.db", "desktop.ini", ".DS_Store"]
junk_ext = ["tmp","crdownload","log"]

def load_rules():
    if rules.exists():
        with open(rules, "r") as f:
            return json.load(f)
    else:
        return default.copy()

def save_rules(rules_dict):
    with open(rules, "w") as f:
        json.dump(rules_dict, f, indent=4)

def load_history():
    if history.exists():
        with open(history, "r") as f:
            return json.load(f)
    else:
        return {}

def save_history(history_dict):
    with open(history, "w") as f:
        json.dump(history_dict, f, indent=4)

def human_size(size, decimal_places=2):
    for unit in ['B','KB','MB','GB','TB']:
        if size < 1024.0:
            return f"{size:.{decimal_places}f} {unit}"
        size /= 1024.0
    return f"{size:.{decimal_places}f} PB"

def clean_filename(name):
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '_')
    return name.strip()

def partial_hash(file_path, num_bytes=1024):
    hasher = base64.b64encode
    with open(file_path, 'rb') as f:
        data = f.read(num_bytes)
        return hasher(data).decode('utf-8')
    
def ensure_dir(path):
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)

def deterministic_category(path, rules):
    name = os.path.basename(path).lower()
    ext = name.split(".")[-1] if "." in name else ""
    size = 0
    try:
        size = os.path.getsize(path)
    except Exception:
        pass
    scores = {cat:0 for cat in rules.keys()}
    for cat, exts in rules.items():
        if ext and ext in exts:
            scores[cat] += 10
    if any(k in name for k in ("screenshot","screen","img","photo")):
        scores["Images"] += 4 if "Images" in scores else 0
    if any(k in name for k in ("invoice","bill","receipt")):
        scores["Docs"] += 5 if "Docs" in scores else 0
    if size > 50_000_000 and "Videos" in scores:
        scores["Videos"] += 4
    best = max(scores.items(), key=lambda kv: kv[1])
    return best[0], scores

def ai(model,message):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    body = {
        "model": model,
        "messages": message
    }
    
    try:
        r = requests.post(api_url, headers=headers, json=body, timeout=30)
        r.raise_for_status()
        response = r.json()
        if isinstance(response, dict):
            return response["choices"][0]["message"]["content"].strip()
        return str(response).strip()
    
    except requests.exceptions.RequestException as e:
        raise Exception(e)

def classify_llm(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            txt = f.read(4000)
    except Exception:
        txt = None

    prompt = (
        "You are a file classification assistant. "
        "Given the filename and a short text excerpt, return ONE best category from this list:\n"
        "- Images\n- Videos\n- Audio\n- Docs\n- Code\n- Archives\n- Misc\n"
        "Return only the single category name and nothing else.\n\n"
        f"Filename: {os.path.basename(path)}\n"
    )
    if txt:
        prompt += f"Text excerpt:\n{txt}\n"

    messages = [{"role":"user","content":prompt}]
    try:
        out = ai(llm, messages)
        if not out or len(out.strip()) == 0:
            return None
        
        lines = out.splitlines()
        if not lines:
            return None
            
        out = lines[0].strip()
        out = out.split(".")[0].strip()
        return out
    except Exception as e:
        print(e)
        return None

def rename_vlm(path):
    try:
        ext = os.path.basename(path).split(".")[-1].lower() if "." in os.path.basename(path) else ""
        mime_types = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "webp": "image/webp",
            "bmp": "image/bmp",
            "svg": "image/svg+xml"
        }
        mime_type = mime_types.get(ext, "image/jpeg")
        with open(path, "rb") as f:
            b = f.read(500_000)
            b64 = base64.b64encode(b).decode()
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text", 
                        "text": "Analyze this image and suggest a SHORT descriptive filename (2-4 words, no extension). Return ONLY the filename."
                    },
                    {
                        "type": "image_url", 
                        "image_url": {
                            "url": f"data:{mime_type};base64,{b64}"
                        }
                    }
                ]
            }
        ]
        
        out = ai(vlm, messages)
        if not out or len(out.strip()) == 0:
            return None
        lines = out.splitlines()
        if not lines:
            return None
        out = lines[0].strip().strip('"').strip("'")
        if "." in out:
            out = out.split(".")[0].strip()
        if len(out) < 2 or len(out) > 100:
            return None
            
        return out
    except Exception as e:
        print(e)
        return None

def rename_clean(path, target_dir):
    base = os.path.basename(path)
    if "." in base:
        name_part = ".".join(base.split(".")[:-1])
        ext = base.split(".")[-1]
    else:
        name_part = base
        ext = ""
    cl = clean_filename(name_part)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    if cl:
        new_base = f"{cl}_{stamp}"
    else:
        new_base = f"file_{stamp}"
    cd = f"{new_base}.{ext}" if ext else new_base
    cpath = os.path.join(target_dir, cd)
    i = 1
    while os.path.exists(cpath):
        cd = f"{new_base}_{i}.{ext}" if ext else f"{new_base}_{i}"
        cpath = os.path.join(target_dir, cd)
        i += 1
    return cpath
def move_file(src, dest_dir):
    ensure_dir(dest_dir)
    dest_path = rename_clean(src, dest_dir)
    shutil.move(src, dest_path)
    return dest_path

def is_junk(path):
    name = os.path.basename(path).lower()
    ext = name.split(".")[-1] if "." in name else ""
    if any(pattern in name for pattern in junk_pattern):
        return True
    if ext in junk_ext:
        return True
    return False

def smart_rename(path, category, use_ai=True):
    if not use_ai:
        return None
    ext = os.path.basename(path).split(".")[-1].lower() if "." in os.path.basename(path) else ""
    if category == "Images" and ext in default["Images"]:
        new_name = rename_vlm(path)
        if new_name:
            return new_name
    if category in ["Docs", "Code"]:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(2000)
            prompt = (
                "You are a file naming assistant. "
                "Based on the content below, suggest a SHORT descriptive filename (2-4 words max, no extension). "
                "Return only the filename, nothing else.\n\n"
                f"Content preview:\n{content[:1000]}\n"
            )
            messages = [{"role":"user","content":prompt}]
            new_name = ai(llm, messages)
            if not new_name or len(new_name.strip()) == 0:
                return None
            lines = new_name.splitlines()
            if not lines:
                return None
            new_name = lines[0].strip().strip('"').strip("'")
            if len(new_name) < 2 or len(new_name) > 100:
                return None
                
            return new_name
        except Exception as e:
            print(e)
            return None
    return None

def sort_directory(source_dir, dest_dir=None):
    source_path = Path(source_dir).resolve()
    if dest_dir:
        dest_path = Path(dest_dir).resolve()
    else:
        dest_path = source_path / "sorted"
    if not source_path.exists():
        return    
    rules_dict = load_rules()
    hist = load_history()
    
    files = [f for f in source_path.iterdir() if f.is_file()]
    
    if not files:
        return
    for file_path in files:
        try:
            file_name = file_path.name
            if is_junk(str(file_path)):
                continue
            category, scores = deterministic_category(str(file_path), rules_dict)
            if scores[category] < 10:
                ai_category = classify_llm(str(file_path))
                if ai_category and ai_category in rules_dict:
                    category = ai_category
            new_name = smart_rename(str(file_path), category)            
            target_dir = dest_path / category            
            ensure_dir(target_dir)
            ext = file_path.suffix
            if new_name:
                clean_name = clean_filename(new_name)
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                base_name = f"{clean_name}_{timestamp}{ext}"
            else:
                base_name = f"{file_path.stem}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
            
            dest_file = target_dir / base_name
            counter = 1
            while dest_file.exists():
                if new_name:
                    clean_name = clean_filename(new_name)
                    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                    base_name = f"{clean_name}_{timestamp}_{counter}{ext}"
                else:
                    base_name = f"{file_path.stem}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{counter}{ext}"
                dest_file = target_dir / base_name
                counter += 1
            shutil.move(str(file_path), str(dest_file))
            hist[str(dest_file)] = {
                "original": str(file_path),
                "category": category,
                "timestamp": datetime.now().isoformat(),
                "ai_renamed": new_name is not None
            }
            print()
        except Exception as e:
            print()
    
    save_history(hist)

def main():
    parser = argparse.ArgumentParser(
        description="Shawtie - AI powered file organization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "source",
        help="Source directory to sort"
    )
    
    parser.add_argument(
        "-o", "--output",
        dest="output",
        help="Output directory (default: source/sorted)"
    )
    
    args = parser.parse_args()
    
    sort_directory(
        source_dir=args.source,
        dest_dir=args.output,
    )

if __name__ == "__main__":
    main()