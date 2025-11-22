"""Command-line interface for Shawtie"""

import argparse
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from .main import sort_directory, show_metadata, show_hist, undo

console = Console()

EXAMPLES = """
[bold cyan]Basic Usage:[/bold cyan]
  shawtie ~/Downloads                    Sort files in Downloads folder
  shawtie ~/Documents --recursive        Sort files including subdirectories
  shawtie ~/Photos -o ~/Organized        Sort to custom output directory

[bold cyan]Preview Before Sorting:[/bold cyan]
  shawtie ~/Downloads --dry-run          Preview what will happen without moving files

[bold cyan]Metadata & History:[/bold cyan]
  shawtie --metadata photo.jpg           Show detailed file information
  shawtie --metadata ~/Pictures          Show metadata for all files in folder
  shawtie --history                      Show sorting history
  shawtie --undo                         Undo last sorting operation

[bold cyan]Options:[/bold cyan]
  shawtie ~/Downloads --no-recursive     Only sort top-level files
  shawtie ~/Music -o ~/Sorted/Music      Custom output directory
"""

def show_examples():
    """Display usage examples"""
    console.print(Panel(
        EXAMPLES,
        title="[bold green]📖 Shawtie Usage Examples[/bold green]",
        border_style="green",
        box=box.ROUNDED,
        padding=(1, 2)
    ))
    
    console.print("\n[bold yellow]📋 Supported File Types:[/bold yellow]\n")
    
    table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
    table.add_column("Category", style="cyan", no_wrap=True)
    table.add_column("Extensions", style="white")
    
    table.add_row("Images", "jpg, png, gif, svg, webp, bmp, tiff")
    table.add_row("Documents", "pdf, doc, docx, txt, md, odt, rtf")
    table.add_row("Videos", "mp4, mkv, mov, avi, webm, flv, wmv")
    table.add_row("Audio", "mp3, wav, flac, aac, ogg, m4a, wma")
    table.add_row("Archives", "zip, rar, tar, gz, 7z, bz2")
    table.add_row("Code", "py, js, java, cpp, c, html, css, json")
    table.add_row("Spreadsheets", "xlsx, xls, csv, ods")
    table.add_row("Presentations", "pptx, ppt, odp")
    
    console.print(table)
    console.print()

def main():
    parser = argparse.ArgumentParser(
        prog="shawtie",
        description="Shawtie - AI-powered file organization tool",
        epilog="For more examples, run: shawtie --examples",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument("source", nargs="?", help="Source directory to sort")
    parser.add_argument("-o", "--output", help="Custom output directory")
    parser.add_argument("-r", "--recursive", action="store_true", default=True, 
                       help="Sort files recursively (default: True)")
    parser.add_argument("--no-recursive", action="store_false", dest="recursive",
                       help="Only sort top-level files")
    parser.add_argument("--dry-run", action="store_true", 
                       help="Preview changes without moving files")
    parser.add_argument("--history", action="store_true", help="Show sorting history")
    parser.add_argument("--undo", action="store_true", help="Undo last sort")
    parser.add_argument("--metadata", metavar="PATH", help="Show file metadata")
    parser.add_argument("--examples", action="store_true", 
                       help="Show usage examples and supported file types")
    parser.add_argument("--version", action="version", version="shawtie 1.0.2")

    args = parser.parse_args()
    
    if args.examples:
        show_examples()
        return
    
    if args.history:
        show_hist()
        return
    
    if args.undo:
        undo()
        return
    
    if args.metadata:
        show_metadata(args.metadata)
        return
    
    if not args.source:
        console.print("[red]Error:[/red] Source directory required")
        console.print("\n[yellow]Tip:[/yellow] Run [cyan]shawtie --help[/cyan] or [cyan]shawtie --examples[/cyan] for usage")
        return
    
    sort_directory(args.source, args.output, args.recursive, dry_run=args.dry_run)

if __name__ == "__main__":
    main()