#!/usr/bin/env python3
"""
Notes App Monitor for macOS
Monitors a specific note in the Notes app and prints changes in real-time.
"""

import sqlite3
import time
import os
from pathlib import Path


class NotesMonitor:
    def __init__(self, folder_name="wenergy", note_name="IPs"):
        self.folder_name = folder_name
        self.note_name = note_name
        self.db_path = self._find_notes_db()
        self.last_content = None
        
    def _find_notes_db(self):
        """Find the Notes database path."""
        home = Path.home()
        # Notes database location on macOS
        db_path = home / "Library" / "Group Containers" / "group.com.apple.notes" / "NoteStore.sqlite"
        
        if not db_path.exists():
            raise FileNotFoundError(
                f"Notes database not found at {db_path}\n"
                "Make sure the Notes app is installed and has been used at least once."
            )
        
        # Check if we can actually read it
        if not os.access(db_path, os.R_OK):
            raise PermissionError(
                f"Cannot read Notes database at {db_path}\n"
                "You need to grant Full Disk Access permission."
            )
        
        return str(db_path)
    
    def _get_note_content(self):
        """
        Read the content of the specified note from the Notes database.
        Returns the note content or None if not found.
        """
        try:
            # Connect to the database (read-only mode)
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            cursor = conn.cursor()
            
            # Query to find the note
            # The Notes database structure:
            # - ZICCLOUDSYNCINGOBJECT contains notes and folders
            # - ZICNOTEDATA contains the actual note content
            
            query = """
            SELECT 
                note.Z_PK,
                note.ZTITLE1,
                data.ZDATA,
                folder.ZTITLE2 as FOLDER_NAME
            FROM ZICCLOUDSYNCINGOBJECT as note
            LEFT JOIN ZICCLOUDSYNCINGOBJECT as folder 
                ON note.ZFOLDER = folder.Z_PK
            LEFT JOIN ZICNOTEDATA as data 
                ON note.ZNOTEDATA = data.Z_PK
            WHERE note.ZTITLE1 IS NOT NULL
                AND note.ZMARKEDFORDELETION = 0
                AND folder.ZTITLE2 = ?
                AND note.ZTITLE1 = ?
            """
            
            cursor.execute(query, (self.folder_name, self.note_name))
            result = cursor.fetchone()
            
            conn.close()
            
            if result:
                note_id, title, data_blob, folder = result
                if data_blob:
                    # The note content is stored as binary data
                    # It contains HTML/RTF formatting, so we need to extract text
                    content = self._extract_text_from_blob(data_blob)
                    return content
            
            return None
            
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            return None
        except Exception as e:
            print(f"Error reading note: {e}")
            return None
    
    def _extract_text_from_blob(self, blob):
        """
        Extract readable text from the Notes binary blob.
        The blob contains protobuf/compressed data with text content.
        """
        try:
            import gzip
            import re
            
            # Try to decompress if it's gzipped
            try:
                decompressed = gzip.decompress(blob)
                blob = decompressed
            except:
                pass
            
            # Convert to string
            text = blob.decode('utf-8', errors='ignore')
            
            # Extract text between common markers or clean up
            # Notes often stores text in a specific format
            # Try to find readable ASCII/UTF-8 sequences
            
            # Method 1: Find sequences of printable characters
            readable_parts = []
            current = []
            
            for char in text:
                if char.isprintable() or char in '\n\r\t':
                    current.append(char)
                else:
                    if len(current) > 3:  # Only keep sequences longer than 3 chars
                        readable_parts.append(''.join(current))
                    current = []
            
            if current and len(current) > 3:
                readable_parts.append(''.join(current))
            
            # Join and clean up
            text = ' '.join(readable_parts)
            
            # Remove excessive whitespace
            text = re.sub(r'\s+', ' ', text)
            text = re.sub(r'\n\s*\n', '\n', text)
            
            # Try to split into lines if there are natural breaks
            # Look for IP-like patterns and separate them
            lines = []
            for part in text.split():
                part = part.strip()
                if part and len(part) > 1:
                    lines.append(part)
            
            result = '\n'.join(lines)
            
            # If result is too messy or too short, try alternative method
            if len(result) < 5 or len([c for c in result if not c.isprintable()]) > len(result) * 0.3:
                # Try regex to find IP addresses or readable text
                ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
                ips = re.findall(ip_pattern, text)
                if ips:
                    return '\n'.join(ips)
                
                # Fall back to finding any sequences of alphanumeric + dots/colons
                readable = re.findall(r'[a-zA-Z0-9.:/_-]{3,}', text)
                if readable:
                    return '\n'.join(readable)
            
            return result if result else text
            
        except Exception as e:
            print(f"Error extracting text: {e}")
            # Last resort: just find printable sequences
            try:
                import re
                text = blob.decode('utf-8', errors='ignore')
                readable = re.findall(r'[a-zA-Z0-9.:/_-]{3,}', text)
                return '\n'.join(readable) if readable else "Error: Could not extract readable text"
            except:
                return "Error: Could not extract readable text"
    
    def print_content(self, content):
        """Print the note content."""
        print("\n" + "="*60)
        print(f"Note: {self.note_name} (Folder: {self.folder_name})")
        print("="*60)
        print(content)
        print("="*60 + "\n")
    
    def detect_changes(self, new_content):
        """
        Detect and print new entries added to the note.
        """
        if self.last_content is None:
            return
        
        # Split into lines and find new ones
        old_lines = set(self.last_content.split('\n'))
        new_lines = set(new_content.split('\n'))
        
        added_lines = new_lines - old_lines
        
        if added_lines:
            print("\n" + "🔔 NEW ENTRY DETECTED " + "🔔")
            print("-" * 60)
            for line in sorted(added_lines):
                if line.strip():  # Only print non-empty lines
                    print(f"➜ {line}")
            print("-" * 60 + "\n")
    
    def monitor(self, interval=2):
        """
        Monitor the note for changes.
        
        Args:
            interval: Check interval in seconds (default: 2)
        """
        print(f"Starting Notes Monitor...")
        print(f"Looking for note '{self.note_name}' in folder '{self.folder_name}'")
        print(f"Database: {self.db_path}")
        print(f"Checking every {interval} seconds. Press Ctrl+C to stop.\n")
        
        try:
            while True:
                content = self._get_note_content()
                
                if content is None:
                    if self.last_content is None:
                        print(f"⚠️  Note '{self.note_name}' not found in folder '{self.folder_name}'")
                        print("Please check that:")
                        print("  1. The Notes app has a folder named 'wenergy'")
                        print("  2. Inside that folder, there's a note named 'IPs'")
                        print(f"\nWill retry in {interval} seconds...")
                    time.sleep(interval)
                    continue
                
                # First time - print the full content
                if self.last_content is None:
                    self.print_content(content)
                    self.last_content = content
                # Check for changes
                elif content != self.last_content:
                    self.detect_changes(content)
                    self.last_content = content
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\nMonitoring stopped by user.")
        except Exception as e:
            print(f"\n❌ Error: {e}")


def list_all_folders_and_notes(db_path):
    """List all folders and notes in the Notes database."""
    try:
        print("\n" + "="*60)
        print("Listing all folders and notes in Notes database")
        print("="*60 + "\n")
        
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.cursor()
        
        # Get all folders
        folder_query = """
        SELECT 
            Z_PK,
            ZTITLE2 as TITLE,
            ZFOLDERTYPE
        FROM ZICCLOUDSYNCINGOBJECT
        WHERE ZTITLE2 IS NOT NULL
            AND ZMARKEDFORDELETION = 0
            AND ZFOLDERTYPE IS NOT NULL
        ORDER BY ZTITLE2
        """
        
        cursor.execute(folder_query)
        folders = cursor.fetchall()
        
        if folders:
            print("📁 FOLDERS:")
            for folder_id, title, folder_type in folders:
                print(f"  • {title} (ID: {folder_id})")
        else:
            print("📁 No folders found")
        
        print("\n" + "-"*60 + "\n")
        
        # Get all notes with their folders
        notes_query = """
        SELECT 
            note.Z_PK,
            note.ZTITLE1 as NOTE_TITLE,
            folder.ZTITLE2 as FOLDER_NAME,
            folder.Z_PK as FOLDER_ID
        FROM ZICCLOUDSYNCINGOBJECT as note
        LEFT JOIN ZICCLOUDSYNCINGOBJECT as folder 
            ON note.ZFOLDER = folder.Z_PK
        WHERE note.ZTITLE1 IS NOT NULL
            AND note.ZMARKEDFORDELETION = 0
        ORDER BY folder.ZTITLE2, note.ZTITLE1
        """
        
        cursor.execute(notes_query)
        notes = cursor.fetchall()
        
        if notes:
            print("📝 NOTES:")
            current_folder = None
            for note_id, note_title, folder_name, folder_id in notes:
                if folder_name != current_folder:
                    current_folder = folder_name
                    folder_display = folder_name if folder_name else "(No Folder)"
                    print(f"\n  In folder: {folder_display}")
                print(f"    ➜ {note_title}")
        else:
            print("📝 No notes found")
        
        print("\n" + "="*60 + "\n")
        
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point."""
    import sys
    
    # Check if user wants to list all folders/notes
    if len(sys.argv) > 1 and sys.argv[1] in ['--list', '-l', 'list']:
        home = Path.home()
        db_path = home / "Library" / "Group Containers" / "group.com.apple.notes" / "NoteStore.sqlite"
        
        if not db_path.exists():
            print(f"❌ Notes database not found at {db_path}")
            return 1
        
        if not os.access(db_path, os.R_OK):
            print(f"❌ Cannot read Notes database (permission denied)")
            print_permission_instructions()
            return 1
        
        list_all_folders_and_notes(str(db_path))
        return 0
    
    # You can customize these values
    FOLDER_NAME = "WEnergy"
    NOTE_NAME = "IPs"
    CHECK_INTERVAL = 2  # seconds
    
    try:
        monitor = NotesMonitor(folder_name=FOLDER_NAME, note_name=NOTE_NAME)
        monitor.monitor(interval=CHECK_INTERVAL)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        print("\nTip: Run with --list to see all available folders and notes")
        return 1
    except PermissionError as e:
        print(f"❌ {e}")
        print_permission_instructions()
        return 1
    
    return 0


def print_permission_instructions():
    """Print instructions for granting Full Disk Access."""
    print("\n" + "="*60)
    print("⚠️  PERMISSION REQUIRED: Full Disk Access")
    print("="*60)
    print("\nTo fix this, you need to grant Full Disk Access:\n")
    print("1. Open System Preferences (or System Settings)")
    print("2. Go to: Privacy & Security → Privacy → Full Disk Access")
    print("3. Click the lock 🔒 icon to make changes")
    print("4. Click the + button and add:")
    print("   • Terminal app (if using system Terminal)")
    print("   • Visual Studio Code (if using VS Code terminal)")
    print("   • Python itself (find it with: which python3)")
    print("5. Check the box to enable it")
    print("6. IMPORTANT: Completely quit and restart the application")
    print("\nAlternative: You can also try running with sudo:")
    print("   sudo python3 /Users/shashank/code/sandbox/py-code/notes_monitor.py")
    print("="*60 + "\n")


if __name__ == "__main__":
    exit(main())
