"""Unreal capture contract for v0.2. No adapter runs in v0.1."""

from __future__ import annotations

from parityforge.errors import HostError


def capture_unreal(*_args: object, **_kwargs: object) -> None:
    raise HostError(
        "Unreal PCG capture is not implemented in ParityForge v0.1.",
        hint=(
            "Editor Python cannot be probed from this package. "
            "See docs/unreal_v0.2.md for the deferred contract. "
            "No Unreal result is produced."
        ),
    )
