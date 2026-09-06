"""Prompt classification, held to the reference's numbers (``src/prompt.rs``).

The decision this module makes is invisible until it is wrong: both branches
produce a running cartridge, and the wrong one produces text that reads like a
bad model rather than like a bug.
"""

from capdag.llm.prompt import (
    DEFAULT_SYSTEM_PROMPT,
    ChatTemplated,
    Raw,
    RefinedDims,
    classify_prompt,
)


def dims_with(chat_template: str) -> RefinedDims:
    return RefinedDims(chat_template=chat_template)


def test_0011_jinja_template_yields_chat_templated():
    """Jinja-template models route through ChatTemplated.

    Forgetting this collapses to Raw, which feeds the chat scaffolding to the
    tokenizer as plain text and produces degenerate output — the model treats
    ``<|im_start|>`` as arbitrary characters instead of a special token.
    """
    strategy = classify_prompt(dims_with("chat-template-jinja"), "Hello", "Be brief")

    assert isinstance(strategy, ChatTemplated)
    assert strategy.system == "Be brief"
    assert strategy.user == "Hello"


def test_0012_short_name_template_yields_chat_templated():
    """``chat-template-short`` — a model naming its template by registered
    short name — must also route through chat templating; the cartridge
    resolves the short name via its backend's template registry."""
    strategy = classify_prompt(dims_with("chat-template-short"), "Hello", None)

    assert isinstance(strategy, ChatTemplated)
    assert strategy.system is None
    assert strategy.user == "Hello"


def test_0013_absent_template_yields_raw():
    """**Core regression guard.** An empty ``chat_template`` means a base /
    completion model, and the cartridge must NOT chat-template the input.

    Routing this way is what made a well-formed instruct model degrade to raw
    completion; routing the other way is the equivalent regression, where the
    rendered ``<|im_start|>`` tokenizes as plain text and corrupts the
    completion.
    """
    strategy = classify_prompt(dims_with(""), "Continue this: once upon", "Be brief")

    assert isinstance(strategy, Raw)
    assert strategy.text == "Continue this: once upon"


def test_0014_whitespace_only_system_prompt_dropped_for_chat_templated():
    """A whitespace-only system prompt is dropped.

    Some templates emit a ``<|im_start|>system\\n\\n<|im_end|>`` envelope around
    an empty body — wasted tokens and a confused turn structure. Both ``""``
    and ``"   "`` collapse to no system turn at all.
    """
    for blank in ("", "   ", "\n\t"):
        strategy = classify_prompt(dims_with("chat-template-jinja"), "Hello", blank)
        assert isinstance(strategy, ChatTemplated)
        assert strategy.system is None, f"{blank!r} must not become a system turn"


def test_0015_unknown_chat_template_value_yields_raw():
    """An unknown ``chat_template`` value falls to Raw.

    A chat-template behaviour is not invented for a tag nobody has classified:
    a future template tag is routed here deliberately rather than sent through
    a backend code path that cannot handle it.
    """
    strategy = classify_prompt(dims_with("chat-template-from-the-future"), "Hi", "sys")

    assert isinstance(strategy, Raw)
    assert strategy.text == "Hi"


def test_0016_default_system_prompt_is_task_agnostic():
    """``DEFAULT_SYSTEM_PROMPT`` works for any input.

    Pinned so that tightening it — inserting task-specific instructions, say —
    is a deliberate commit rather than an accidental one.
    """
    assert DEFAULT_SYSTEM_PROMPT.startswith("You are a helpful assistant.")
    lowered = DEFAULT_SYSTEM_PROMPT.lower()
    for task in ("summar", "translat", "json", "code"):
        assert task not in lowered, f"the default prompt has become {task}-specific"
