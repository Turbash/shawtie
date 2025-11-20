import os
import base64
import json
import requests
import sys
import time
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
    r = requests.post(api_url, headers=headers, json=body)
    r.raise_for_status()
    response = r.json()
    return response.choices[0].message.content.strip()

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
        out = out.splitlines()[0].strip()
        out = out.split(".")[0].strip()
        return out
    except Exception as e:
        print(e)
        return None

def rename_vlm(path):
    try:
        with open(path, "rb") as f:
            b = f.read(2_000_000)
            b64 = base64.b64encode(b).decode()
    except Exception:
        return None
    messages = [
        {
            "role": "user",
            "content": [
                {"type":"text", "text": "You are a file classifier. Given the filename and the image, return best name for the file"},
                {"type":"text", "text": f"Filename: {os.path.basename(path)}"},
                {"type":"image_url", "image_url": f"data:image;base64,{b64}"},
            ]
        }
    ]
    try:
        out = ai(vlm, messages)
        out = out.splitlines()[0].strip()
        out = out.split(".")[0].strip()
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

