"""Memory compression utilities.

Compresses working memory files to keep only the most recent high-quality entries,
moving older entries to memory-archive.md for historical reference.
"""

from pathlib import Path
from datetime import datetime
import re
import os

from .. import memory

ARCHIVE_PATH = memory.MEMORY_DIR / "memory-archive.md"
MEMORY_DIR = memory.MEMORY_DIR


def compress_memory_file(file_path: Path, keep_recent: int = 10) -> int:
    """
    Compress a memory file to keep only the most recent N entries.
    
    Args:
        file_path: Path to the memory file (e.g., facts.md)
        keep_recent: Number of recent entries to keep (default: 10)
        
    Returns:
        Number of entries moved to archive
    """
    if not file_path.exists():
        return 0
    
    content = file_path.read_text(encoding="utf-8")
    lines = content.split("\n")
    
    # Parse entries (format: [agent][timestamp] content)
    entry_pattern = re.compile(r'^\[(\w+)\]\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})\]\s+(.+)$')
    entries = []
    header_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        match = entry_pattern.match(line)
        if match:
            agent, timestamp, content_text = match.groups()
            entries.append({
                "agent": agent,
                "timestamp": timestamp,
                "content": content_text,
                "original_line": line
            })
        elif line.startswith("#"):
            header_lines.append(line)
    
    # Sort by timestamp (most recent first)
    entries.sort(key=lambda e: e["timestamp"], reverse=True)
    
    # Split into keep vs archive
    to_keep = entries[:keep_recent]
    to_archive = entries[keep_recent:]
    
    # Rewrite the working memory file with only recent entries
    with open(file_path, "w", encoding="utf-8") as f:
        for header in header_lines:
            f.write(header + "\n")
        f.write("\n")
        for entry in to_keep:
            f.write(entry["original_line"] + "\n")
    
    # Append archived entries to memory-archive.md
    if to_archive:
        with open(ARCHIVE_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n## Archived from {file_path.name} on {datetime.now().isoformat()[:16]}\n\n")
            for entry in to_archive:
                f.write(entry["original_line"] + "\n")
    
    return len(to_archive)


def compress_all_memory_files(keep_recent: int = 10) -> dict:
    """
    Compress all memory files (facts, learnings, decisions).
    
    Args:
        keep_recent: Number of recent entries to keep per file
        
    Returns:
        Dict with counts of archived entries per file
    """
    results = {}
    
    for filename in ["facts.md", "learnings.md", "decisions.md"]:
        file_path = MEMORY_DIR / filename
        if file_path.exists():
            archived_count = compress_memory_file(file_path, keep_recent)
            results[filename] = archived_count
    
    return results


def query_archive(keyword: str, category: str = None, limit: int = 10) -> list:
    """
    Query the memory archive for entries matching a keyword.
    
    Args:
        keyword: Search term to find in archived entries
        category: Optional filter (facts/learnings/decisions)
        limit: Maximum number of results to return
        
    Returns:
        List of matching archive entries
    """
    if not ARCHIVE_PATH.exists():
        return []
    
    content = ARCHIVE_PATH.read_text(encoding="utf-8")
    lines = content.split("\n")
    
    entry_pattern = re.compile(r'^\[(\w+)\]\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})\]\s+(.+)$')
    matches = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        match = entry_pattern.match(line)
        if match:
            agent, timestamp, content_text = match.groups()
            
            # Check keyword match (case-insensitive)
            if keyword.lower() not in content_text.lower():
                continue
            
            # Check category filter if specified
            if category:
                # Infer category from file context (simplified)
                # In practice, you'd want to track which file each entry came from
                pass
            
            matches.append({
                "agent": agent,
                "timestamp": timestamp,
                "content": content_text,
                "full_line": line
            })
            
            if len(matches) >= limit:
                break
    
    return matches


def get_archive_stats() -> dict:
    """
    Get statistics about the memory archive.
    
    Returns:
        Dict with archive statistics
    """
    if not ARCHIVE_PATH.exists():
        return {"total_entries": 0, "categories": {}}
    
    content = ARCHIVE_PATH.read_text(encoding="utf-8")
    lines = content.split("\n")
    
    entry_pattern = re.compile(r'^\[(\w+)\]\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})\]\s+(.+)$')
    categories = {}
    total = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        match = entry_pattern.match(line)
        if match:
            agent, timestamp, content_text = match.groups()
            total += 1
            categories[agent] = categories.get(agent, 0) + 1
    
    return {
        "total_entries": total,
        "categories": categories
    }


if __name__ == "__main__":
    # Example usage
    print("Compressing memory files...")
    results = compress_all_memory_files(keep_recent=10)
    for filename, count in results.items():
        print(f"  {filename}: archived {count} entries")
    
    print("\nArchive stats:")
    stats = get_archive_stats()
    print(f"  Total archived entries: {stats['total_entries']}")
    print(f"  By category: {stats['categories']}")
