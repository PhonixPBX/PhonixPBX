"""Pure configuration generators: ``Snapshot`` in, list of ``GeneratedFile`` out."""

from __future__ import annotations

from askozia.generators import asterisk, system
from askozia.generators.base import Facts, GeneratedFile, Secrets, Snapshot, build_snapshot


def generate_all(snap: Snapshot) -> list[GeneratedFile]:
    files = [*asterisk.generate(snap), *system.generate(snap)]
    paths = [f.path for f in files]
    assert len(paths) == len(set(paths)), "duplicate generated path"
    return files


__all__ = ["Facts", "GeneratedFile", "Secrets", "Snapshot", "build_snapshot", "generate_all"]
