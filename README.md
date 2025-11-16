# File Migration Utility

A utility to help sort through files migrating from various clouds. This tool identifies duplicate files in your inbox directory that already exist elsewhere (excluding the archive) and moves them to a timestamped archive folder.

## Features

- **Duplicate Detection**: Uses file size and SHA256 hash to identify identical files
- **Efficient Scanning**: Only computes hashes for files with matching sizes
- **Preserves Structure**: Maintains directory structure when moving files to archive
- **Automatic Cleanup**: Removes empty directories from inbox after migration
- **Safe Operation**: Only moves files that are confirmed duplicates

## Usage

```bash
python migrate_files.py <inbox_dir> <search_dir1> [search_dir2 ...] [--archive <archive_dir>]
```

### Arguments

- `inbox_dir`: The directory containing files to check for duplicates
- `search_dir1`, `search_dir2`, ...: Directories to search for existing files (archive is automatically excluded)
- `--archive <archive_dir>`: (Optional) Specify the archive directory. If not provided, defaults to `archive/` in the parent directory of inbox

### Examples

```bash
# Basic usage - search in documents and photos directories
python migrate_files.py inbox/ documents/ photos/

# Specify custom archive directory
python migrate_files.py inbox/ documents/ photos/ --archive my_archive/

# Search in multiple directories
python migrate_files.py inbox/ documents/ photos/ videos/ music/
```

## How It Works

1. **Indexing Phase**: The utility scans all specified search directories (excluding archive) and builds an index of files by size and hash
2. **Comparison Phase**: For each file in the inbox, it:
   - Checks if any file with the same size exists
   - If size matches, computes the SHA256 hash
   - Compares the hash to find exact duplicates
3. **Migration Phase**: Duplicate files are moved to `archive/YYYY-MM-DD-HH-MM-migration/` preserving the directory structure from inbox
4. **Cleanup Phase**: Empty directories in the inbox are removed

## Archive Structure

Files are moved to:
```
archive/
└── YYYY-MM-DD-HH-MM-migration/
    └── [preserved inbox directory structure]/
        └── file.ext
```

Only directories that contain files are created in the archive.

## Notes

- The archive directory can contain multiple copies of the same files (as intended)
- Files are compared by both size and content hash for accuracy
- The utility will skip files it cannot read or hash
- Empty folders in inbox are automatically deleted after migration

