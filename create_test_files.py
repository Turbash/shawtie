from pathlib import Path

def create_test_directory():
    test_dir = Path("test_files")
    test_dir.mkdir(exist_ok=True)
    
    docs = {
        "random_notes.txt": "These are some random notes about my day. Meeting at 3pm tomorrow.",
        "recipe_chocolate_cake.txt": """
            Chocolate Cake Recipe
            Ingredients:
            - 2 cups flour
            - 1 cup sugar
            - 3/4 cup cocoa powder
            - 2 eggs
            - 1 cup milk
            Instructions:
            Mix all ingredients and bake at 350°F for 30 minutes.
        """,
        "invoice_2024.txt": """
            INVOICE #12345
            Date: November 20, 2025
            Bill To: John Doe
            Amount Due: $1,500.00
            Services rendered for consulting work.
        """,
        "meeting_notes.docx": "Mock DOCX file - Meeting notes from Q4 planning session",
        "project_proposal.pdf": "Mock PDF file - Project proposal for new website redesign",
    }
    
    for f, content in docs.items():
        with open(test_dir / f, "w") as f:
            f.write(content)
    code_files = {
        "calculator.py": """
            def add(a, b):
                return a + b

            def subtract(a, b):
                return a - b

            if __name__ == "__main__":
                print(add(5, 3))
        """,
        "app.js": """
            const express = require('express');
            const app = express();

            app.get('/', (req, res) => {
                res.send('Hello World!');
            });

            app.listen(3000);
        """,
        "styles.css": """
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #f0f0f0;
            }

            .container {
                max-width: 1200px;
                margin: 0 auto;
            }
        """,
        "config.json": """{
            "api_url": "https://kriyan.eryzalabs.com",
            "timeout": 5000,
            "retries": 3
        }""",
        "README.md": """
            # Shambhavi Rauthan

            Don't Readme.

            ## Contacts
            - Email: shambhavi@eryzalabs.com
            - Phone: +91XXXXXXXXXX
        """,
    }
    
    for f, c in code_files.items():
        with open(test_dir / f, "w") as f:
            f.write(c)
    image_files = {
        "screenshot_2024.png": b"\x89PNG\r\n\x1a\n" + b"Mock PNG image data" * 100,
        "photo_vacation.jpg": b"\xff\xd8\xff\xe0" + b"Mock JPEG image data" * 100,
        "diagram.svg": """<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
    <circle cx="50" cy="50" r="40" fill="blue"/>
</svg>""".encode(),
        "profile_picture.webp": b"RIFF" + b"\x00" * 4 + b"WEBP" + b"Mock WebP data" * 50,
    }
    
    for f, c in image_files.items():
        with open(test_dir / f, "wb") as f:
            f.write(c)
    media_files = {
        "tutorial_video.mp4": b"Mock MP4 video file content" * 1000,
        "presentation.mov": b"Mock MOV video file content" * 1000,
        "song.mp3": b"ID3" + b"Mock MP3 audio data" * 500,
        "podcast_episode.wav": b"RIFF" + b"\x00" * 4 + b"WAVE" + b"Mock WAV data" * 500,
    }
    
    for f, c in media_files.items():
        with open(test_dir / f, "wb") as f:
            f.write(c)
    archive_files = {
        "backup.zip": b"PK\x03\x04" + b"Mock ZIP archive" * 100,
        "source_code.tar.gz": b"\x1f\x8b\x08" + b"Mock GZIP archive" * 100,
        "files.7z": b"7z\xbc\xaf\x27\x1c" + b"Mock 7z archive" * 100,
    }
    
    for f, content in archive_files.items():
        with open(test_dir / f, "wb") as f:
            f.write(c)
    junk_files = {
        "Thumbs.db": b"Mock Windows thumbnail cache",
        ".DS_Store": b"Mock macOS metadata",
        "temp_file.tmp": b"Temporary file content",
        "download.crdownload": b"Incomplete Chrome download",
        "debug.log": "2024-11-20 10:30:45 DEBUG: Application started\n" * 50,
    }

    for f, c in junk_files.items():
        mode = "wb" if isinstance(c, bytes) else "w"
        with open(test_dir / f, mode) as f:
            f.write(c)
    misc_files = {
        "no_extension_file": "This file has no extension",
        "weird.xyz": "Unknown file type",
    }
    
    for f, c in misc_files.items():
        with open(test_dir / f, "w") as f:
            f.write(c)
    
if __name__ == "__main__":
    create_test_directory()
