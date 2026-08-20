# CapDAG for Python

This public package is the Python mirror of CapDAG. It provides Tagged, Media,
and Cap URNs; capability definitions; registry resolution; Machine Notation;
planning and execution; Bifaci; and the Python cartridge runtime and CLI.

Rust is the behavioral reference. Shared numbered tests carry the same meaning
across mirrors, so current test catalogues—not a prose count—record parity.

## Install the package

Python 3.11 or newer is required.

```bash
python3 -m pip install capdag
```

For a source checkout:

```bash
python3 -m pip install -e '.[dev]'
```

## Parse and build Cap URNs

```python
from capdag import CapUrn, CapUrnBuilder

parsed = CapUrn.from_string(
    'cap:disbind;in="media:ext=pdf";out="media:enc=utf-8;page"'
)
built = (
    CapUrnBuilder()
    .in_spec("media:ext=pdf")
    .out_spec("media:enc=utf-8;page")
    .marker("disbind")
    .build()
)

assert parsed.to_string() == built.to_string()
```

Treat URNs as opaque parsed values. Use their predicates for equivalence,
conformance, dispatch, and ranking rather than splitting or comparing their
serialized strings.

## Find the relevant API

The package follows the boundaries in the
[CapDAG specification](https://github.com/machinefabric/capdag/blob/main/docs/01-overview.md):

- `capdag.urn` contains Tagged, Media, and Cap URNs;
- `capdag.cap` contains definitions, argument sources, schema validation, and
  callers;
- `capdag.machine` and `capdag.planner` contain notation, planning, and
  execution structures;
- `capdag.bifaci` contains frames, streaming, flow control, cartridge and host
  runtimes, and relay components; and
- registry modules resolve versioned fabric and cartridge data.

Docstrings beside public Python objects are the language-specific API
reference. Language-neutral rules belong to the canonical specification.

## Scaffold a Python cartridge

```bash
capdag new sentiment-tagger --python
cd sentiment-tagger
capdag dev-install .
echo "I love this" | capdag sentiment-tagger
```

The generated project demonstrates a manifest, canonical URNs, handler
registration, typed input and output, a model-backed peer call, and progress
forwarding. See [Build and Run a Cartridge](https://github.com/machinefabric/capdag/blob/main/docs/18.2-getting-started-cartridge-development.md).

## Verify changes

```bash
python3 -m pytest
```

Run `python3 -m pytest --cov=capdag` when you also need a coverage report.
Shared behavior changes require the applicable reference test with the same
substantive number and assertions.

## License

MIT
