import os
import base64
import json
import requests
import shutil
import argparse
import time
from pathlib import Path
from datetime import datetime
from pydub import AudioSegment
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn, TimeElapsedColumn
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()

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
            b = f.read(500000)
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

def transcribe_audio(path):
    try:
        try:
            audio = AudioSegment.from_file(path)
            duration_seconds = len(audio) / 1000.0
            duration_str = f"{int(duration_seconds // 60)}m {int(duration_seconds % 60)}s"
            sample_rate = audio.frame_rate
            channels = audio.channels
            file_size = os.path.getsize(path)
            size_mb = file_size / (1024 * 1024)
            filename = os.path.basename(path)
            prompt = (
                "You are a file naming assistant for audio files. "
                "Analyze the filename and audio properties to suggest a SHORT descriptive filename (2-4 words max, no extension). "
                "Infer the type of content from patterns:\n"
                "- Voice recordings/memos: usually mono, short duration, small size\n"
                "- Music: usually stereo, higher bitrate, longer duration\n"
                "- Podcasts: usually mono or stereo, medium duration\n"
                "- Sound effects: usually very short\n"
                "Look for keywords in the filename like 'record', 'voice', 'memo', 'music', 'song', etc.\n"
                "Be creative but accurate. Return only the filename, nothing else.\n\n"
                f"Original filename: {filename}\n"
                f"Duration: {duration_str}\n"
                f"Sample rate: {sample_rate}Hz\n"
                f"Channels: {'Stereo' if channels == 2 else 'Mono'}\n"
                f"File size: {size_mb:.1f}MB\n"
            )
            messages = [{"role":"user","content":prompt}]
            renamed = ai(llm, messages)
            if not renamed or len(renamed.strip()) == 0:
                return None
            lines = renamed.splitlines()
            if not lines:
                return None
            renamed = lines[0].strip().strip('"').strip("'")
            if renamed.lower().startswith("filename:"):
                renamed = renamed[9:].strip()
            if "." in renamed:
                renamed = renamed.split(".")[0].strip()
            if len(renamed) < 2 or len(renamed) > 100:
                return None
            return renamed
        except Exception as e:
            print(e)
            return None
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
    c_path = os.path.join(target_dir, cd)
    i = 1
    while os.path.exists(c_path):
        cd = f"{new_base}_{i}.{ext}" if ext else f"{new_base}_{i}"
        c_path = os.path.join(target_dir, cd)
        i += 1
    return c_path

def move_file(src, dest_dir):
    ensure_dir(dest_dir)
    dest = rename_clean(src, dest_dir)
    shutil.move(src, dest)
    return dest

def is_junk(path):
    name = os.path.basename(path).lower()
    ext = name.split(".")[-1] if "." in name else ""
    if any(pattern in name for pattern in junk_pattern):
        return True
    if ext in junk_ext:
        return True
    return False

def smart_rename(path, cat, use_ai=True):
    if not use_ai:
        return None
    ext = os.path.basename(path).split(".")[-1].lower() if "." in os.path.basename(path) else ""
    if cat == "Images" and ext in default["Images"]:
        renamed = rename_vlm(path)
        if renamed:
            return renamed
    if cat == "Audio" and ext in default["Audio"]:
        renamed = transcribe_audio(path)
        if renamed:
            return renamed
    if cat in ["Docs", "Code"]:
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
            renamed = ai(llm, messages)
            if not renamed or len(renamed.strip()) == 0:
                return None
            lines = renamed.splitlines()
            if not lines:
                return None
            renamed = lines[0].strip().strip('"').strip("'")
            if len(renamed) < 2 or len(renamed) > 100:
                return None
            return renamed
        except Exception as e:
            print(e)
            return None
    return None

def sort_directory(source_dir, dest_dir=None, recursive=True):
    source = Path(source_dir).resolve()
    if dest_dir:
        dest = Path(dest_dir).resolve()
    else:
        dest = source / "sorted"
    if not source.exists():
        return    
    
    rules_dict = load_rules()
    hist = load_history()
    if recursive:
        files = []
        for root, dirs, filenames in os.walk(source):
            root_path = Path(root)
            if dest in root_path.parents or root_path == dest:
                continue
            for filename in filenames:
                files.append(root_path / filename)
    else:
        files = [f for f in source.iterdir() if f.is_file()]
    
    if not files:
        return
    
    stats = {
        "sorted": 0,
        "skipped": 0,
        "errors": 0,
        "by_category": {},
        "ai_renamed": 0,
        "total_size": 0
    }
    with Progress(SpinnerColumn(),TextColumn("[prog.description]{task.description}"),BarColumn(),TextColumn("[prog.percentage]{task.percentage:>3.0f}%"),TextColumn("•"),TextColumn("[cyan]{task.completed}/{task.total}[/cyan]"),TextColumn("•"),TimeElapsedColumn(),TextColumn("•"),TimeRemainingColumn(),console=console) as prog:

        task = prog.add_task("[cyan]Sorting files...", total=len(files))
        for f in files:
            try:
                file_display = f.name[:40] + "..." if len(f.name) > 40 else f.name
                prog.update(task, description=f"[cyan]Sorting:[/cyan] [yellow]{file_display}[/yellow]")
                if is_junk(str(f)):
                    stats["skipped"] += 1
                    prog.advance(task)
                    continue
                try:
                    stats["total_size"] += f.stat().st_size
                except:
                    pass
                cat, scores = deterministic_category(str(f), rules_dict)
                if scores[cat] < 10:
                    ai_cat = classify_llm(str(f))
                    if ai_cat and ai_cat in rules_dict:
                        cat = ai_cat
                renamed = smart_rename(str(f), cat)
                if renamed:
                    stats["ai_renamed"] += 1
                target_dir = dest / cat
                ensure_dir(target_dir)
                ext = f.suffix
                if renamed:
                    clean_name = clean_filename(renamed)
                    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                    base_name = f"{clean_name}_{timestamp}{ext}"
                else:
                    base_name = f"{f.stem}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
                dest_file = target_dir / base_name
                counter = 1
                while dest_file.exists():
                    if renamed:
                        clean_name = clean_filename(renamed)
                        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                        base_name = f"{clean_name}_{timestamp}_{counter}{ext}"
                    else:
                        base_name = f"{f.stem}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{counter}{ext}"
                    dest_file = target_dir / base_name
                    counter += 1
                shutil.move(str(f), str(dest_file))
                hist[str(dest_file)] = {
                    "original": str(f),
                    "category": cat,
                    "timestamp": datetime.now().isoformat(),
                    "ai_renamed": renamed is not None
                }
                stats["sorted"] += 1
                stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1
            except Exception as e:
                stats["errors"] += 1
            prog.advance(task)
    
    save_history(hist)
    if recursive:
        cleanup_empty_dirs(source, dest)
    console.print()
    summary_text = f"[green] Successfully sorted:[/green] [bold]{stats['sorted']}[/bold] files"
    
    if stats["errors"] > 0:
        summary_text += f"\n[red]Errors:[/red] [bold]{stats['errors']}[/bold] files"
    console.print(Panel(summary_text, title="[green][bold]COMPLETED![/bold][/green]", 
                        border_style="green", box=box.DOUBLE))
    if stats["by_category"]:
        table = Table(title="\nFiles by Category", box=box.ROUNDED, show_header=True, 
                     header_style="bold cyan")
        table.add_column("Category", style="cyan", no_wrap=True)
        table.add_column("Files", justify="right", style="green")
        table.add_column("Percentage", justify="right", style="yellow")
        
        sorted_cats = sorted(stats["by_category"].items(), key=lambda x: x[1], reverse=True)
        for cat, count in sorted_cats:
            percentage = (count / stats["sorted"] * 100) if stats["sorted"] > 0 else 0
            table.add_row(cat, str(count), f"{percentage:.1f}%")
        
        console.print(table)
        console.print()

def cleanup_empty_dirs(source, dest):
    for root, dirs, files in os.walk(source, topdown=False):
        root_path = Path(root)
        if root_path == source or root_path == dest or dest in root_path.parents:
            continue
        try:
            if not any(root_path.iterdir()):
                root_path.rmdir()
                console.print(f"  [dim]🗑️  Removed empty directory: {root_path.relative_to(source)}[/dim]")
        except (OSError, ValueError):
            pass

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
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        default=True,
        help="Sort files in subdirectories recursively (default: True)"
    )
    parser.add_argument(
        "--no-recursive",
        action="store_false",
        dest="recursive",
        help="Only sort files in the top-level directory"
    )
    args = parser.parse_args()
    sort_directory(
        source_dir=args.source,
        dest_dir=args.output,
        recursive=args.recursive,
    )

if __name__ == "__main__":
    main()