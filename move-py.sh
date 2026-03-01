#!/bin/bash
cd /Users/bahram/ws/prj/machinefabric/capdag-py

# Create module directories
mkdir -p src/capdag/urn src/capdag/cap src/capdag/media src/capdag/bifaci

# URN module
git mv src/capdag/cap_urn.py src/capdag/urn/cap_urn.py
git mv src/capdag/media_urn.py src/capdag/urn/media_urn.py
git mv src/capdag/cap_matrix.py src/capdag/urn/cap_matrix.py

# Cap module
git mv src/capdag/cap.py src/capdag/cap/definition.py
git mv src/capdag/caller.py src/capdag/cap/caller.py
git mv src/capdag/response.py src/capdag/cap/response.py
git mv src/capdag/registry.py src/capdag/cap/registry.py
git mv src/capdag/validation.py src/capdag/cap/validation.py
git mv src/capdag/schema_validation.py src/capdag/cap/schema_validation.py

# Media module
git mv src/capdag/media_spec.py src/capdag/media/spec.py
git mv src/capdag/media_registry.py src/capdag/media/registry.py

# Bifaci module
git mv src/capdag/cbor_frame.py src/capdag/bifaci/frame.py
git mv src/capdag/cbor_io.py src/capdag/bifaci/io.py
git mv src/capdag/manifest.py src/capdag/bifaci/manifest.py
git mv src/capdag/plugin_runtime.py src/capdag/bifaci/plugin_runtime.py
git mv src/capdag/plugin_host_runtime.py src/capdag/bifaci/host_runtime.py
git mv src/capdag/async_plugin_host.py src/capdag/bifaci/async_plugin_host.py
git mv src/capdag/plugin_relay.py src/capdag/bifaci/relay.py
git mv src/capdag/relay_switch.py src/capdag/bifaci/relay_switch.py

# Create __init__.py files for new modules
touch src/capdag/urn/__init__.py
touch src/capdag/cap/__init__.py
touch src/capdag/media/__init__.py
touch src/capdag/bifaci/__init__.py

echo "File reorganization complete. Now update imports in src/capdag/__init__.py"
