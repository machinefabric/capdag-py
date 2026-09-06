"""Prompt preparation for instruction-tuned LLMs.

Every instruct/chat-tuned model carries a ``tokenizer.chat_template`` in its
metadata that frames a user message with the special-token scaffolding the
model was trained on. Feeding such a model raw user text — without the template
— produces degenerate output: the model reads the bytes as an arbitrary
continuation and (especially with a fixed seed) collapses to the same
high-prior completion whatever the input was.

``cap:download-model`` returns a :class:`RefinedDims` view of the model's
detected dim profile alongside the local path. The consuming cap reads
``chat_template`` from that view and calls :func:`classify_prompt` to decide
how to prepare its tokenizer input:

- ``chat-template-jinja`` / ``chat-template-short`` → :class:`ChatTemplated` —
  the cartridge MUST render the user message (and optional system prompt)
  through the model's own chat-template machinery and tokenize the rendered
  string with special-token parsing enabled. Each backend has its own
  chat-template surface, so the rendering stays in the cartridge; only the
  DECISION is shared.
- empty / ``chat-template-absent`` → :class:`Raw` — the model is a
  base/completion model. The user prompt is tokenized verbatim: no specials,
  and no system prompt, because a base model has no notion of one.

The system-prompt argument on each text-generation cap defaults to
:data:`DEFAULT_SYSTEM_PROMPT`. A cap author who wants a task-specific default
overrides it in the cap TOML's ``default_value``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

__all__ = [
    "DEFAULT_SYSTEM_PROMPT",
    "RefinedDims",
    "ChatTemplated",
    "Raw",
    "PromptStrategy",
    "classify_prompt",
]


#: The system prompt baked into every text-generation cap when the caller
#: supplies none. Generic enough to frame any input — code, prose, JSON, a
#: transcript — as a request for a useful response. Concrete instructions
#: (summarise, translate, explain) belong in the user turn.
DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful assistant. Respond to the user's input with a useful, accurate, "
    "and concise reply. If the input is a document or excerpt, treat it as the subject "
    "of the user's request and respond about it."
)


@dataclass
class RefinedDims:
    """The dim profile of a downloaded model, as far as prompting cares.

    Built by the consuming cartridge from what ``cap:download-model`` answered.
    The strings are the kebab-case dim values (``"chat-template-jinja"``,
    ``"chat-template-short"``, ``""`` for absent) — the same wire form as the
    ``media:model-spec`` URN tags.
    """

    #: The wire ``chat_template`` field. Empty means the model carries no chat
    #: template at all, which makes it a base / completion model.
    chat_template: str = ""
    #: The wire ``family`` field. Not consulted here; carried so a cartridge
    #: can branch on family without re-deriving it.
    family: str = ""
    #: The wire ``model_task`` field — ``llm`` / ``vision`` / ``embeddings``.
    #: Not consulted here; carried so the dims live in one place.
    model_task: str = ""


@dataclass(frozen=True)
class ChatTemplated:
    """The model expects chat-formatted input.

    The cartridge MUST render the system and user turns through the model's
    chat-template machinery and tokenize the result with special-token parsing
    on. This carries the raw turn texts; the cartridge owns the rendering,
    because every backend's API for it differs.
    """

    #: The system turn, or ``None`` when there is none. Chat templates accept
    #: zero or one system message.
    system: Optional[str]
    #: The user's message. Non-empty by contract — an empty user turn is
    #: refused upstream by the cap's required stdin argument.
    user: str


@dataclass(frozen=True)
class Raw:
    """The model has no chat template.

    Tokenize the text as a raw completion prompt. Any system prompt is dropped:
    a base model has no notion of a system message, and prepending one as plain
    text corrupts the completion-style invocation.
    """

    #: The user's text, fed to the tokenizer verbatim.
    text: str


#: What :func:`classify_prompt` decides.
PromptStrategy = Union[ChatTemplated, Raw]


def classify_prompt(
    dims: RefinedDims, user: str, system: Optional[str] = None
) -> PromptStrategy:
    """Decide how to prepare a user prompt for a model with these dims.

    ``system`` is the system prompt to use: a non-empty string is rendered as
    the system turn (chat-templated) or dropped (raw); ``None`` or a blank
    string means the caller wanted none. The default to fall back to before
    calling here is :data:`DEFAULT_SYSTEM_PROMPT`.

    ``user`` is the prompt text. An empty one is the caller's bug and is not
    checked for: the cap surface already declares the argument as required.
    """
    # The chat-template axis values that demand templated rendering. The
    # catalogue defines `chat-template-jinja` and `chat-template-short`; an
    # empty string means absent, so the model is a base / completion model. Any
    # OTHER value is unknown and falls to raw — an unfamiliar future template
    # tag must not be fed silently through chat formatting that does not apply
    # to it.
    if dims.chat_template in ("chat-template-jinja", "chat-template-short"):
        # An empty system string is dropped: a caller may pass "" to mean "I
        # have no system prompt", and some templates render an empty system
        # turn as a whole `<|im_start|>system\n\n<|im_end|>` envelope — wasted
        # tokens around a turn that says nothing.
        cleaned = system if system and system.strip() else None
        return ChatTemplated(system=cleaned, user=user)
    return Raw(text=user)
