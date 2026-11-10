"""Tests for the Python capdag CLI: its commands, what it prints where, its
errors and its exit statuses, as the reference CLI defines them.

Tests use TEST###: comments matching the Rust implementation for cross-tracking.
"""

import json

from capdag import cli


def run(capsys, *args):
    """Run the CLI as ``capdag <args>``; its exit status, stdout and stderr."""
    status = cli.main(["capdag", *args])
    out, err = capsys.readouterr()
    return status, out, err


# TEST8167: `dev new <path> --lang <language>` makes the project at that path,
# prints its directory alone on stdout, and says on stderr what to type next;
# under --json the result is one `project` record.
def test_8167_dev_new_makes_the_project_and_says_what_next(tmp_path, capsys):
    status, out, err = run(capsys, "dev", "new", str(tmp_path / "mood"), "--lang", "python")
    assert status == 0
    assert out == f"{tmp_path / 'mood'}\n"
    assert (tmp_path / "mood").is_dir()
    assert "Made the Python cartridge 'mood'" in err
    assert "  capdag dev install\n" in err
    assert "capdag run mood" in err

    status, out, err = run(capsys, "--json", "dev", "new", str(tmp_path / "tone"), "--lang", "python")
    assert status == 0
    assert err == ""
    assert json.loads(out) == {"type": "project", "dir": str(tmp_path / "tone"), "language": "python"}


# TEST8168: a usage mistake exits 2 — an unknown command, a missing --lang, a
# language no stub is vendored for, a --fabric that is not a URL — and the
# --fabric error says what is wrong and what to give instead.
def test_8168_usage_mistakes_exit_2(tmp_path, capsys):
    assert run(capsys, "resolve", "disbind-pdf")[0] == 2
    assert run(capsys, "dev", "new", str(tmp_path / "mood"))[0] == 2
    assert run(capsys, "dev", "new", str(tmp_path / "mood"), "--lang", "cobol")[0] == 2
    assert not (tmp_path / "mood").exists()

    status, out, err = run(capsys, "--fabric", "fabric.example", "cache", "clear")
    assert status == 2
    assert out == ""
    assert err == (
        "error: --fabric 'fabric.example' is not an http(s) URL\n"
        "hint: for example: --fabric https://fabric-staging.capdag.com\n"
    )


# TEST8169: a command that fails exits 1 with `error:` and what it found on
# stderr, and under --json also writes the error as one record on stdout.
def test_8169_a_failure_exits_1_and_says_why(tmp_path, capsys):
    (tmp_path / "mood").mkdir()

    status, out, err = run(capsys, "dev", "new", str(tmp_path / "mood"), "--lang", "python")
    assert status == 1
    assert out == ""
    assert err.startswith(f"error: the project {tmp_path / 'mood'} could not be made\n  ")

    status, out, err = run(capsys, "--json", "dev", "new", str(tmp_path / "mood"), "--lang", "python")
    assert status == 1
    record = json.loads(out)
    assert record["type"] == "error"
    assert record["problem"] == f"the project {tmp_path / 'mood'} could not be made"
    assert record["exit"] == 1
    assert len(record["context"]) == 1


# TEST8170: `dev install` of a directory that holds no built project says so,
# and says to build it first.
def test_8170_dev_install_of_an_unbuilt_project_says_to_build_it(tmp_path, capsys):
    status, out, err = run(capsys, "dev", "install", str(tmp_path))
    assert status == 1
    assert out == ""
    assert err.startswith(f"error: {tmp_path} is not a cartridge project that is built\n")
    assert err.endswith("hint: build it first, as `capdag dev new` said; then run this again\n")
