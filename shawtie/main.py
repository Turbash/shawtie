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
from rich.tree import Tree
from PIL import Image
from PIL.ExifTags import TAGS
import mimetypes

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

def sort_directory(source_dir, dest_dir=None, recursive=True, dry_run=False):
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
    
    if dry_run:
        console.print(f"\n[bold yellow]🔍 DRY RUN MODE - No files will be moved[/bold yellow]\n")
        preview_table = Table(title="Preview of Changes", box=box.ROUNDED, show_header=True)
        preview_table.add_column("File", style="cyan", no_wrap=False)
        preview_table.add_column("→", style="white", justify="center")
        preview_table.add_column("Category", style="green")
        preview_table.add_column("New Location", style="yellow", no_wrap=False)
        
        for f in files[:50]:
            if is_junk(str(f)):
                continue
            cat, scores = deterministic_category(str(f), rules_dict)
            target_dir = dest / cat
            preview_table.add_row(
                f.name,
                "→",
                cat,
                str(target_dir.relative_to(source))
            )
        
        console.print(preview_table)
        
        total_files = len([f for f in files if not is_junk(str(f))])
        total_size = sum(f.stat().st_size for f in files if not is_junk(str(f)))
        
        console.print(f"\n[bold]Summary:[/bold]")
        console.print(f"  Total files to sort: [cyan]{total_files}[/cyan]")
        console.print(f"  Total size: [cyan]{human_size(total_size)}[/cyan]")
        console.print(f"  Destination: [cyan]{dest}[/cyan]")
        console.print(f"\n[yellow]💡 Run without --dry-run to actually move files[/yellow]\n")
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
                print(e)
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
        tab = Table(title="\nFiles by Category", box=box.ROUNDED, show_header=True, 
                     header_style="bold cyan")
        tab.add_column("Category", style="cyan", no_wrap=True)
        tab.add_column("Files", justify="right", style="green")
        tab.add_column("Percentage", justify="right", style="yellow")
        sorted_cats = sorted(stats["by_category"].items(), key=lambda x: x[1], reverse=True)
        for cat, count in sorted_cats:
            percentage = (count / stats["sorted"] * 100) if stats["sorted"] > 0 else 0
            tab.add_row(cat, str(count), f"{percentage:.1f}%")

        console.print(tab)
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
        nargs="?",
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
    parser.add_argument(
        "--history",
        action="store_true",
        help="Show sorting history"
    )
    parser.add_argument(
        "--undo",
        action="store_true",
        help="Undo the most recent sorting operation"
    )
    parser.add_argument(
        "--metadata",
        metavar="PATH",
        help="Show detailed metadata for a file or directory"
    )
    parser.add_argument(
        "--meta",
        metavar="PATH",
        dest="metadata",
        help="Alias for --metadata"
    )
    args = parser.parse_args()
    if args.history:
        show_hist()
        return
    if args.undo:
        undo()
        return
    if args.metadata:
        show_metadata(args.metadata)
        return
    if args.source is None:
        console.print("[red]Error:[/red] Source directory is required.")
        return
    sort_directory(
        source_dir=args.source,
        dest_dir=args.output,
        recursive=args.recursive,
    )


def show_hist():
    hist = load_history()
    if not hist:
        console.print("[yellow]No history found.[/yellow]")
        return
    sessions = {}
    for dest, info in hist.items():
        timestamp = info.get("timestamp", "unknown")
        date = timestamp.split("T")[0] if "T" in timestamp else timestamp
        if date not in sessions:
            sessions[date] = []
        sessions[date].append((dest, info))
    tab = Table(title="Sorting History", box=box.ROUNDED, show_header=True, header_style="bold magenta")
    tab.add_column("Date", style="magenta", no_wrap=True)
    tab.add_column("Files Sorted", style="green", justify="right")
    tab.add_column("Renamed", style="cyan", justify="right")
    totalfiles = 0
    totalrenamed = 0
    for date in sorted(sessions.keys(), reverse=True):
        files = sessions[date]
        renamed = sum(1 for _, info in files if info.get("ai_renamed", False))
        tab.add_row(date, str(len(files)), str(renamed))
        totalfiles += len(files)
        totalrenamed += renamed
    console.print(tab)
    console.print(f"[bold]Total files sorted:[/bold] {totalfiles}")
    console.print(f"[bold]Total files renamed:[/bold] {totalrenamed}")

def undo():
    hist = load_history()
    if not hist:
        console.print("[yellow] No history found.[/yellow]")
        return
    recents = sorted(hist.items(), key=lambda x: x[1].get("timestamp", ""), reverse=True)
    if not recents:
        console.print("[yellow] No history found.[/yellow]")
        return
    timestamp = sorted(hist.values(), key=lambda x: x.get("timestamp", ""), reverse=True)[0].get("timestamp", "")
    date = timestamp.split("T")[0] if "T" in timestamp else timestamp
    to_undo = {k:v for k,v in hist.items() if v.get("timestamp","").startswith(date)}
    if not to_undo:
        console.print("[yellow] No files to undo.[/yellow]")
        return
    console.print(f"[cyan] Undoing sorting for date:[/cyan] [bold]{date}[/bold]")
    for dest, info in to_undo.items():
        original = info.get("original", None)
        if original and os.path.exists(dest):
            ensure_dir(Path(original).parent)
            shutil.move(dest, original)
            console.print(f"  [green]↩️  Moved back:[/green] {Path(dest).name} → {original}")
            del hist[dest]
    save_history(hist)
    console.print("[bold]Undo successful.[/bold]")


def get_metadata(path):
    path = Path(path)
    if not path.exists():
        return None
    meta = {
        "filename": path.name,
        "path": str(path.absolute()),
        "size": path.stat().st_size,
        "size_human": human_size(path.stat().st_size),
        "created": datetime.fromtimestamp(path.stat().st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
        "modified": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "accessed": datetime.fromtimestamp(path.stat().st_atime).strftime("%Y-%m-%d %H:%M:%S"),
        "extension": path.suffix,
        "mime_type": mimetypes.guess_type(str(path))[0] or "unknown",
    }
    if path.suffix.lower() in [".jpg", ".jpeg", ".png", ".tiff", ".bmp", ".gif", ".webp"]:
        try:
            img = Image.open(path)
            meta["image"] = {
                "width": img.width,
                "height": img.height,
                "format": img.format,
                "mode": img.mode,
            }
            data = img._getexif()
            if data:
                exif = {}
                for tag_id, value in data.items():
                    tag = TAGS.get(tag_id, tag_id)
                    if isinstance(value, bytes):
                        continue
                    exif[tag] = str(value)[:100]
                meta["exif"] = {
                    "camera": exif.get("Model", "Unknown"),
                    "date_taken": exif.get("DateTime", "Unknown"),
                    "iso": exif.get("ISOSpeedRatings", "Unknown"),
                    "exposure": exif.get("ExposureTime", "Unknown"),
                    "aperture": exif.get("FNumber", "Unknown"),
                    "focal_length": exif.get("FocalLength", "Unknown"),
                    "gps": f"{exif.get('GPSLatitude', 'N/A')}, {exif.get('GPSLongitude', 'N/A')}"
                }
        except Exception as e:
            meta["image_error"] = str(e)
            
    if path.suffix.lower() in ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a']:
        try:
            audio = AudioSegment.from_file(path)
            duration = len(audio) / 1000.0
            meta["audio"] = {
                "duration": f"{int(duration // 60)}m {int(duration % 60)}s",
                "sample_rate": f"{audio.frame_rate}Hz",
                "channels": "Stereo" if audio.channels == 2 else "Mono",
                "bits_per_sample": audio.sample_width * 8,
            }
            if path.suffix.lower() == '.mp3':
                try:
                    from mutagen.mp3 import MP3
                    from mutagen.id3 import ID3
                    audio_file = MP3(path)
                    meta["audio"]["bitrate"] = f"{audio_file.info.bitrate // 1000}kbps"
                    if audio_file.tags:
                        id3 = audio_file.tags
                        meta["id3"] = {
                            "title": str(id3.get("TIT2", "Unknown")),
                            "artist": str(id3.get("TPE1", "Unknown")),
                            "album": str(id3.get("TALB", "Unknown")),
                            "year": str(id3.get("TDRC", "Unknown")),
                            "genre": str(id3.get("TCON", "Unknown")),
                        }
                except ImportError:
                    pass
                except Exception:
                    pass
        except Exception as e:
            meta["audio_error"] = str(e)
            
    if path.suffix.lower() in ['.mp4', '.mkv', '.mov', '.avi', '.webm', '.flv']:
        try:
            import subprocess
            result = subprocess.run(
                ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', str(path)],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                video_info = json.loads(result.stdout)
                if 'format' in video_info:
                    fmt = video_info['format']
                    meta["video"] = {
                        "duration": f"{float(fmt.get('duration', 0)):.2f}s",
                        "bitrate": f"{int(fmt.get('bit_rate', 0)) // 1000}kbps",
                        "format": fmt.get('format_name', 'Unknown'),
                    }
                for stream in video_info.get('streams', []):
                    if stream.get('codec_type') == 'video':
                        meta["video"]["resolution"] = f"{stream.get('width', 0)}x{stream.get('height', 0)}"
                        meta["video"]["codec"] = stream.get('codec_name', 'Unknown')
                        meta["video"]["fps"] = stream.get('avg_frame_rate', 'Unknown')
                        break
        except Exception as e:
            meta["video_error"] = str(e)
    return meta


def display_metadata(meta):
    if not meta:
        console.print("[red]Could not read metadata[/red]")
        return
    info_text = f"""[bold cyan]Filename:[/bold cyan] {meta['filename']}
    [bold cyan]Path:[/bold cyan] {meta['path']}
    [bold cyan]Size:[/bold cyan] {meta['size_human']} ({meta['size']:,} bytes)
    [bold cyan]Type:[/bold cyan] {meta['mime_type']}
    [bold cyan]Extension:[/bold cyan] {meta['extension']}
    [bold yellow]Timestamps:[/bold yellow]
    Created:  {meta['created']}
    Modified: {meta['modified']}
    Accessed: {meta['accessed']}"""
    console.print(Panel(info_text, title="[bold green]File Information[/bold green]", 
                        border_style="green", box=box.ROUNDED))
    console.print()
    if "image" in meta:
        img_info = meta["image"]
        img_text = f"[bold cyan]Dimensions:[/bold cyan] {img_info['width']}x{img_info['height']}\n"
        img_text += f"[bold cyan]Format:[/bold cyan] {img_info['format']}\n"
        img_text += f"[bold cyan]Color Mode:[/bold cyan] {img_info['mode']}"
        console.print(Panel(img_text, title="[bold magenta]Image Properties[/bold magenta]", 
                          border_style="magenta", box=box.ROUNDED))
        console.print()
        if "exif" in meta:
            exif = meta["exif"]
            exif_table = Table(title="EXIF Data", box=box.SIMPLE, show_header=False)
            exif_table.add_column("Property", style="cyan", no_wrap=True)
            exif_table.add_column("Value", style="white")
            exif_table.add_row("Camera", exif.get("camera", "N/A"))
            exif_table.add_row("Date Taken", exif.get("date_taken", "N/A"))
            exif_table.add_row("ISO", exif.get("iso", "N/A"))
            exif_table.add_row("Exposure", exif.get("exposure", "N/A"))
            exif_table.add_row("Aperture", exif.get("aperture", "N/A"))
            exif_table.add_row("Focal Length", exif.get("focal_length", "N/A"))
            exif_table.add_row("GPS Location", exif.get("gps", "N/A"))
            console.print(exif_table)
            console.print()
    if "audio" in meta:
        audio_info = meta["audio"]
        audio_text = f"[bold cyan]Duration:[/bold cyan] {audio_info['duration']}\n"
        audio_text += f"[bold cyan]Sample Rate:[/bold cyan] {audio_info['sample_rate']}\n"
        audio_text += f"[bold cyan]Channels:[/bold cyan] {audio_info['channels']}\n"
        audio_text += f"[bold cyan]Bits per Sample:[/bold cyan] {audio_info['bits_per_sample']}"
        if "bitrate" in audio_info:
            audio_text += f"\n[bold cyan]Bitrate:[/bold cyan] {audio_info['bitrate']}"
        console.print(Panel(audio_text, title="[bold blue]🎵 Audio Properties[/bold blue]", 
                          border_style="blue", box=box.ROUNDED))
        console.print()
        if "id3" in meta:
            id3 = meta["id3"]
            id3_table = Table(title="ID3 Tags", box=box.SIMPLE, show_header=False)
            id3_table.add_column("Tag", style="cyan", no_wrap=True)
            id3_table.add_column("Value", style="white")
            id3_table.add_row("Title", id3.get("title", "N/A"))
            id3_table.add_row("Artist", id3.get("artist", "N/A"))
            id3_table.add_row("Album", id3.get("album", "N/A"))
            id3_table.add_row("Year", id3.get("year", "N/A"))
            id3_table.add_row("Genre", id3.get("genre", "N/A"))
            console.print(id3_table)
            console.print()
    if "video" in meta:
        video_info = meta["video"]
        video_text = f"[bold cyan]Duration:[/bold cyan] {video_info.get('duration', 'N/A')}\n"
        video_text += f"[bold cyan]Resolution:[/bold cyan] {video_info.get('resolution', 'N/A')}\n"
        video_text += f"[bold cyan]Codec:[/bold cyan] {video_info.get('codec', 'N/A')}\n"
        video_text += f"[bold cyan]FPS:[/bold cyan] {video_info.get('fps', 'N/A')}\n"
        video_text += f"[bold cyan]Bitrate:[/bold cyan] {video_info.get('bitrate', 'N/A')}\n"
        video_text += f"[bold cyan]Format:[/bold cyan] {video_info.get('format', 'N/A')}"
        console.print(Panel(video_text, title="[bold red]Video Properties[/bold red]", 
                          border_style="red", box=box.ROUNDED))
        console.print()


def show_metadata(path):
    p = Path(path)
    if not p.exists():
        console.print(f"[red]Path not found: {path}[/red]")
        return
    if p.is_file():
        console.print(f"\n[bold green]Reading metadata for:[/bold green] {p.name}\n")
        metadata = get_metadata(p)
        display_metadata(metadata)
    else:
        files = list(p.rglob('*')) if p.is_dir() else []
        files = [f for f in files if f.is_file()]
        if not files:
            console.print("[yellow] No files found in directory[/yellow]")
            return
        console.print(f"\n[bold green]Found {len(files)} files[/bold green]\n")
        for i, file in enumerate(files, 1):
            console.print(f"\n[bold cyan]═══ File {i}/{len(files)} ═══[/bold cyan]\n")
            metadata = get_metadata(file)
            display_metadata(metadata) 
            if i < len(files):
                console.print("\n" + "─" * 80 + "\n")