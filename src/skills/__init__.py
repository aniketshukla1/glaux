"""Glaux skill synthesis & curation (Phase 4).

- :func:`static_cap_check` — AST guard that rejects code beyond declared caps.
- :class:`SkillSynthesizer` — LLM proposes a skill + tests; tests run sandboxed.
- :class:`SkillLibrary` — quarantine → promote/deprecate lifecycle + versioning
  over procedural memory.
"""

from .capcheck import static_cap_check
from .library import (
    DEPRECATED,
    PENDING_APPROVAL,
    PROMOTED,
    QUARANTINED,
    REJECTED,
    SkillLibrary,
    SkillRecord,
    is_sensitive,
)
from .synthesize import SkillCandidate, SkillSynthesizer, SynthesisResult

__all__ = [
    "static_cap_check",
    "SkillSynthesizer",
    "SkillCandidate",
    "SynthesisResult",
    "SkillLibrary",
    "SkillRecord",
    "is_sensitive",
    "QUARANTINED",
    "PROMOTED",
    "DEPRECATED",
    "PENDING_APPROVAL",
    "REJECTED",
]
