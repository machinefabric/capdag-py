"""Charters for tests: prod and lab charters of each kind, stored as an
installer stores them.

The signature beside a stored charter is opaque here: this mirror carries it
and never reads it (see ``capdag/bifaci/charter.py``).
"""

import json
from pathlib import Path
from typing import Optional

from capdag.bifaci.charter import (
    CHARTER_FILE,
    CHARTER_FORMAT,
    CHARTER_SIG_FILE,
    Charter,
    FetchedCharter,
    RegistryKind,
    store_charter,
)

CARTRIDGES_ANCHOR = "https://registry.example/cartridges"
CARTRIDGES_SLUG = "example-cartridges"
LAB_ANCHOR = "https://lab.example/exp/t1/cartridges"


def cartridges_charter(anchor: str = CARTRIDGES_ANCHOR, slug: str = CARTRIDGES_SLUG) -> Charter:
    """A prod cartridges charter at ``anchor``, named ``slug``."""
    return Charter(
        format=CHARTER_FORMAT,
        anchor=anchor,
        kind=RegistryKind.CARTRIDGES,
        slug=slug,
        environment="prod",
        locations={"manifest": f"{anchor}/v{{registry_version}}/manifest"},
        issued_at=1_792_800_000,
        not_after=None,
        fabric="https://registry.example/fabric",
    )


def fabric_charter(anchor: str, slug: str) -> Charter:
    """A prod fabric charter at ``anchor``, named ``slug``."""
    return Charter(
        format=CHARTER_FORMAT,
        anchor=anchor,
        kind=RegistryKind.FABRIC,
        slug=slug,
        environment="prod",
        locations={
            "manifest": f"{anchor}/manifest/{{manifest_version}}.json",
            "latest": f"{anchor}/manifest/latest.json",
            "definition": f"{anchor}/{{kind}}/{{urn_hash}}/{{version}}.json",
        },
        issued_at=1_792_800_000,
        not_after=None,
    )


def lab_charter() -> Charter:
    """A lab cartridges charter, with an expiry of its own."""
    charter = cartridges_charter(LAB_ANCHOR, "lab-t1-cartridges")
    charter.environment = "lab"
    charter.experiment = "t1"
    charter.not_after = 1_800_576_000
    return charter


def fetched(charter: Charter) -> FetchedCharter:
    """``charter`` as its anchor would serve it."""
    return FetchedCharter(
        charter=charter,
        body=json.dumps(charter.to_dict()).encode("utf-8"),
        signature=b'{"format":"machinefabric-charter-sig/1"}',
    )


def store_test_charter(root: Path, folder: str, charter: Optional[Charter] = None) -> None:
    """Store ``charter`` (the example cartridges charter by default) in
    ``{root}/{folder}``, as an installer does. ``store_charter`` refuses a
    folder not named for the slug, so a test that stores under another name
    writes the files itself."""
    charter = charter if charter is not None else cartridges_charter()
    f = fetched(charter)
    if folder == charter.slug:
        store_charter(f, Path(root) / folder)
        return
    d = Path(root) / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / CHARTER_FILE).write_bytes(f.body)
    (d / CHARTER_SIG_FILE).write_bytes(f.signature)
