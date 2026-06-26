"""Tests for collection input folder hierarchies."""

from capdag.planner.collection_input import CapInputCollection, CollectionFile


# TEST716: Tests CapInputCollection empty collection has zero files and folders Verifies is_empty() returns true and counts are zero for new collection
def test_716_empty_collection():
    collection = CapInputCollection("root", "Root")
    assert collection.is_empty()
    assert collection.total_file_count() == 0
    assert collection.total_folder_count() == 0


# TEST717: Tests CapInputCollection correctly counts files in flat collection Verifies total_file_count() returns 2 for collection with 2 files, no folders
def test_717_collection_with_files():
    collection = CapInputCollection("root", "Root")
    collection.files = [
        CollectionFile("1", "/tmp/a.pdf", "media:pdf"),
        CollectionFile("2", "/tmp/b.md", "media:enc=utf-8;ext=md"),
    ]
    assert collection.total_file_count() == 2
    assert collection.total_folder_count() == 0


# TEST718: Tests CapInputCollection correctly counts files and folders in nested structure Verifies total_file_count() includes subfolder files and total_folder_count() counts subfolders
def test_718_nested_collection():
    root = CapInputCollection("root", "Root")
    root.files = [CollectionFile("1", "/tmp/a.pdf", "media:pdf")]

    subfolder = CapInputCollection("sub", "Sub")
    subfolder.files = [CollectionFile("2", "/tmp/b.pdf", "media:pdf")]
    root.folders["sub"] = subfolder

    assert root.total_file_count() == 2
    assert root.total_folder_count() == 1


# TEST719: Tests CapInputCollection flatten_to_files recursively collects all files Verifies flatten() extracts files from root and all subfolders into flat list
def test_719_flatten_to_files():
    root = CapInputCollection("root", "Root")
    root.files = [CollectionFile("1", "/tmp/a.pdf", "media:pdf")]

    subfolder = CapInputCollection("sub", "Sub")
    subfolder.files = [CollectionFile("2", "/tmp/b.pdf", "media:text")]
    root.folders["sub"] = subfolder

    files = root.flatten_to_files()
    assert len(files) == 2
    assert files[0].file_path == "/tmp/a.pdf"
    assert files[0].source_id == "1"
    assert files[1].file_path == "/tmp/b.pdf"
    assert files[1].source_id == "2"


# TEST933: Tests CapInputCollection serializes to JSON and deserializes correctly Verifies JSON round-trip preserves folder_id, folder_name, files and file metadata
def test_933_serialization_roundtrip():
    collection = CapInputCollection("folder-123", "Test Folder")
    collection.files.append(
        CollectionFile("listing-1", "/path/to/file.pdf", "media:pdf").with_title("My Document")
    )
    roundtrip = CapInputCollection.from_dict(collection.to_json())
    assert roundtrip.folder_id == collection.folder_id
    assert roundtrip.folder_name == collection.folder_name
    assert len(roundtrip.files) == 1
    assert roundtrip.files[0].title == "My Document"
