#!/usr/bin/env python3
"""
File Migration Utility

This utility helps sort through files migrating from various clouds.
It identifies files in the inbox directory that already exist elsewhere
(excluding archive) and moves them to a timestamped archive folder.
"""

import argparse
import os
import sys
import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, Set, Tuple, Optional, List, Iterable


@dataclass
class MigrationResult:
    """Summary of a migration run."""

    moved_files: int
    failed_files: int
    duplicate_files: List[Path]
    migration_folder: Optional[Path]
    archive_dir: Path


def compute_file_hash(file_path: Path, chunk_size: int = 8192) -> Optional[str]:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            while chunk := f.read(chunk_size):
                sha256.update(chunk)
        return sha256.hexdigest()
    except (IOError, OSError) as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
        return None


def get_file_size(file_path: Path) -> Optional[int]:
    """Get file size in bytes."""
    try:
        return file_path.stat().st_size
    except (OSError, IOError) as e:
        print(f"Error getting size for {file_path}: {e}", file=sys.stderr)
        return None


def build_file_index(
    directory: Path,
    exclude_dirs: Optional[Set[str]] = None,
    exclude_paths: Optional[Set[Path]] = None,
) -> Dict[Tuple[int, str], Path]:
    """
    Build an index of files by (size, hash).
    This is more efficient - we compute hashes only for files with matching sizes.
    """
    if exclude_dirs is None:
        exclude_dirs = set()
    if exclude_paths is None:
        exclude_paths = set()
    
    file_index: Dict[Tuple[int, str], Path] = {}
    exclude_dirs_lower = {d.lower() for d in exclude_dirs}
    exclude_paths_abs = {Path(p).resolve() for p in exclude_paths}
    
    print(f"Indexing files in {directory}...")
    scanned = 0
    hashed = 0
    
    # First pass: group by size
    size_groups = defaultdict(list)
    
    for root, dirs, files in os.walk(directory):
        root_path = Path(root).resolve()
        
        # Skip if this path is in exclude_paths or is a subdirectory
        if root_path in exclude_paths_abs:
            dirs[:] = []
            continue
        # Skip if this path is a subdirectory of any exclude_path
        if any(str(root_path).startswith(str(exclude_path) + os.sep) 
               for exclude_path in exclude_paths_abs):
            dirs[:] = []
            continue
        
        # Skip if any part of the path matches exclude_dirs
        if any(part.lower() in exclude_dirs_lower for part in root_path.parts):
            dirs[:] = []
            continue
        
        for file in files:
            file_path = root_path / file
            if not file_path.is_file():
                continue
            
            scanned += 1
            if scanned % 100 == 0:
                print(f"  Scanned {scanned} files, hashed {hashed}...", end='\r')
            
            size = get_file_size(file_path)
            if size is None:
                continue
            
            size_groups[size].append(file_path)
    
    # Second pass: compute hashes for files with matching sizes
    for size, file_paths in size_groups.items():
        if len(file_paths) == 1:
            # Only one file with this size, compute hash anyway for comparison
            file_path = file_paths[0]
            file_hash = compute_file_hash(file_path)
            if file_hash:
                file_index[(size, file_hash)] = file_path
                hashed += 1
        else:
            # Multiple files with same size, compute hashes
            for file_path in file_paths:
                file_hash = compute_file_hash(file_path)
                if file_hash:
                    file_index[(size, file_hash)] = file_path
                    hashed += 1
    
    print(f"\n  Indexed {scanned} files, computed {hashed} hashes.")
    return file_index


def find_duplicates(
    inbox_dir: Path,
    search_dirs: List[Path],
    archive_dir: Path
) -> Dict[Path, bool]:
    """
    Find files in inbox that are duplicates of files in search_dirs.
    Returns: {inbox_file_path: is_duplicate}
    """
    print("\n" + "="*60)
    print("Building index of existing files (excluding archive)...")
    print("="*60)
    
    # Build index of all files in search directories (excluding archive)
    exclude_dirs = {archive_dir.name}
    exclude_paths = {archive_dir.resolve()}
    existing_files: Dict[Tuple[int, str], Path] = {}
    
    for search_dir in search_dirs:
        if not search_dir.exists():
            print(f"Warning: Search directory {search_dir} does not exist, skipping.")
            continue
        index = build_file_index(search_dir, exclude_dirs, exclude_paths)
        existing_files.update(index)
    
    print(f"\nFound {len(existing_files)} unique files in search directories.")

    size_to_hashes: Dict[int, Set[str]] = defaultdict(set)
    for size, file_hash in existing_files.keys():
        size_to_hashes[size].add(file_hash)
    
    print("\n" + "="*60)
    print("Checking inbox files for duplicates...")
    print("="*60)
    
    duplicates = {}
    inbox_files = []
    
    # Collect all files in inbox
    for root, dirs, files in os.walk(inbox_dir):
        root_path = Path(root)
        for file in files:
            file_path = root_path / file
            if file_path.is_file():
                inbox_files.append(file_path)
    
    print(f"Checking {len(inbox_files)} files in inbox...")
    
    for i, inbox_file in enumerate(inbox_files):
        if (i + 1) % 10 == 0:
            print(f"  Checked {i + 1}/{len(inbox_files)} files...", end='\r')
        
        size = get_file_size(inbox_file)
        if size is None:
            duplicates[inbox_file] = False
            continue
        
        # Check if any file with same size exists
        matching_hashes = size_to_hashes.get(size)

        if not matching_hashes:
            # No file with same size, definitely not a duplicate
            duplicates[inbox_file] = False
            continue
        
        # Compute hash of inbox file
        inbox_hash = compute_file_hash(inbox_file)
        if inbox_hash is None:
            duplicates[inbox_file] = False
            continue
        
        # Check if exact match exists
        if inbox_hash in matching_hashes:
            duplicates[inbox_file] = True
        else:
            duplicates[inbox_file] = False
    
    print(f"\n  Checked {len(inbox_files)} files.")
    duplicate_count = sum(1 for is_dup in duplicates.values() if is_dup)
    print(f"  Found {duplicate_count} duplicate files.")
    
    return duplicates


def move_to_archive(
    file_path: Path,
    inbox_dir: Path,
    archive_dir: Path,
    migration_folder: Path
) -> bool:
    """
    Move file to archive, preserving directory structure relative to inbox.
    """
    try:
        # Get relative path from inbox
        relative_path = file_path.relative_to(inbox_dir)
        
        # Create destination path in migration folder
        dest_path = migration_folder / relative_path
        
        # Create parent directories
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Move file
        shutil.move(str(file_path), str(dest_path))
        
        return True
    except Exception as e:
        print(f"Error moving {file_path} to archive: {e}", file=sys.stderr)
        return False


def remove_empty_dirs(directory: Path):
    """Remove empty directories in the given directory."""
    removed = 0
    for root, dirs, files in os.walk(directory, topdown=False):
        root_path = Path(root)
        if root_path == directory:
            continue  # Don't remove the root directory itself
        
        try:
            # Check if directory is empty
            if not any(root_path.iterdir()):
                root_path.rmdir()
                removed += 1
        except OSError:
            pass  # Directory not empty or other error
    
    if removed > 0:
        print(f"Removed {removed} empty directories from inbox.")


def migrate_duplicates(
    inbox_dir: Path,
    search_dirs: Iterable[Path],
    archive_dir: Optional[Path] = None,
    *,
    timestamp: Optional[str] = None,
) -> MigrationResult:
    """Run the migration process and return a summary of the work performed."""

    inbox_dir = Path(inbox_dir)
    search_dirs = [Path(d) for d in search_dirs]

    if not search_dirs:
        raise ValueError("At least one search directory must be provided.")

    if not inbox_dir.exists() or not inbox_dir.is_dir():
        raise FileNotFoundError(f"Inbox directory {inbox_dir} does not exist or is not a directory.")

    if archive_dir is None:
        archive_dir = inbox_dir.parent / "archive"

    archive_dir = archive_dir.resolve()
    archive_dir.mkdir(parents=True, exist_ok=True)

    for search_dir in search_dirs:
        if not search_dir.exists() or not search_dir.is_dir():
            print(f"Warning: Search directory {search_dir} does not exist or is not a directory.")

    duplicates = find_duplicates(inbox_dir, search_dirs, archive_dir)
    duplicate_files = [path for path, is_dup in duplicates.items() if is_dup]

    if not duplicate_files:
        print("\nNo duplicate files found. Nothing to migrate.")
        return MigrationResult(0, 0, [], None, archive_dir)

    migration_timestamp = timestamp or datetime.now().strftime("%Y-%m-%d-%H-%M")
    migration_folder = archive_dir / f"{migration_timestamp}-migration"
    migration_folder.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"Moving {len(duplicate_files)} duplicate files to archive...")
    print(f"Migration folder: {migration_folder}")
    print(f"{'='*60}")

    moved = 0
    failed = 0

    for i, file_path in enumerate(duplicate_files):
        if (i + 1) % 10 == 0:
            print(f"  Moved {i + 1}/{len(duplicate_files)} files...", end='\r')

        if move_to_archive(file_path, inbox_dir, archive_dir, migration_folder):
            moved += 1
        else:
            failed += 1

    print(f"\n  Moved {moved} files successfully.")
    if failed > 0:
        print(f"  Failed to move {failed} files.")

    print(f"\n{'='*60}")
    print("Cleaning up empty directories...")
    print(f"{'='*60}")
    remove_empty_dirs(inbox_dir)

    print(f"\n{'='*60}")
    print("Migration complete!")
    print(f"{'='*60}")

    return MigrationResult(moved, failed, duplicate_files, migration_folder, archive_dir)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description="Move duplicate files from an inbox to an archive directory.")
    parser.add_argument("inbox_dir", type=Path, help="Directory containing files to analyze")
    parser.add_argument(
        "search_dirs",
        nargs="+",
        type=Path,
        help="Directories to search for existing files (duplicates)",
    )
    parser.add_argument(
        "--archive",
        type=Path,
        help="Optional archive directory. Defaults to '<inbox_parent>/archive'.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    """CLI entrypoint."""

    args = parse_args(argv)

    print("=" * 60)
    print("File Migration Utility")
    print("=" * 60)
    print(f"Inbox directory: {args.inbox_dir}")
    print(f"Search directories: {', '.join(str(d) for d in args.search_dirs)}")
    print(f"Archive directory: {args.archive or args.inbox_dir.parent / 'archive'}")
    print("=" * 60)

    try:
        result = migrate_duplicates(args.inbox_dir, args.search_dirs, args.archive)
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    if not result.duplicate_files:
        return

    print(f"\nSummary: moved {result.moved_files} files to {result.migration_folder}")
    if result.failed_files:
        print(f"Failures: {result.failed_files}")


if __name__ == "__main__":
    main()
