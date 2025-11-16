from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pytest

from migrate_files import migrate_duplicates, compute_file_hash


@pytest.fixture
def sample_dirs(tmp_path):
    inbox = tmp_path / "inbox"
    search = tmp_path / "docs"
    archive = tmp_path / "archive"
    inbox.mkdir()
    search.mkdir()
    archive.mkdir()
    return inbox, search, archive


def create_file(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def test_migrate_duplicates_moves_only_exact_matches(sample_dirs):
    inbox, search, archive = sample_dirs

    original = create_file(search / "notes" / "todo.txt", "finish migration tool")
    duplicate = create_file(inbox / "notes" / "todo.txt", "finish migration tool")
    create_file(inbox / "unique.txt", "one of a kind")

    result = migrate_duplicates(
        inbox,
        [search],
        archive,
        timestamp="2023-01-01-00-00",
    )

    assert result.moved_files == 1
    assert result.failed_files == 0
    assert duplicate in result.duplicate_files
    migrated_copy = archive / "2023-01-01-00-00-migration" / "notes" / "todo.txt"
    assert migrated_copy.exists()
    assert compute_file_hash(migrated_copy) == compute_file_hash(original)
    assert (inbox / "unique.txt").exists()
    assert not (inbox / "notes" / "todo.txt").exists()
    # Empty inbox directories should be removed
    assert not (inbox / "notes").exists()


def test_no_duplicates_skips_creating_migration_folder(sample_dirs):
    inbox, search, archive = sample_dirs

    create_file(inbox / "a.txt", "alpha")
    create_file(search / "b.txt", "beta")

    result = migrate_duplicates(
        inbox,
        [search],
        archive,
        timestamp="2023-01-01-00-00",
    )

    assert result.moved_files == 0
    assert result.failed_files == 0
    assert result.migration_folder is None
    assert (archive / "2023-01-01-00-00-migration").exists() is False
    assert (inbox / "a.txt").exists()
