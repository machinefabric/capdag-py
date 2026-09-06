"""Talking to a language model.

:mod:`capdag.llm.protocol` holds the canonical types for the LLM media defs —
one half of a definition capdag itself declares, which is why they belong here
rather than in a package that could version away from them.
:mod:`capdag.llm.prompt` decides how a downloaded model wants its input framed,
from the dim profile ``cap:download-model`` returns beside the local path.

These types carry the same field names, the same defaults and the same wire
form as the Rust mirror's, because a cap answered by a Python cartridge must be
indistinguishable on the wire from the same cap answered by a Rust one.

This was ``capdag-cartridge-sdk``, a separate package per language. One of its
modules was never about language models at all and did not come with it: the
page/index grammar is :mod:`capdag.pages`.
"""

from . import prompt, protocol

__all__ = ["prompt", "protocol"]
