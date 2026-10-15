from pathlib import Path

from parityforge.hosts.invocation import (
    BLENDER_CAPTURE_EXAMPLE,
    BLENDER_DEMO_EXAMPLE,
    HOUDINI_CAPTURE_EXAMPLE,
    HOUDINI_DEMO_EXAMPLE,
)


def test_readme_documents_the_commands_the_scripts_implement() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    for command in (
        BLENDER_CAPTURE_EXAMPLE,
        HOUDINI_CAPTURE_EXAMPLE,
        BLENDER_DEMO_EXAMPLE,
        HOUDINI_DEMO_EXAMPLE,
    ):
        assert command in readme
    assert "ICP" in Path("docs/architecture.md").read_text(encoding="utf-8")
    assert "NOT_RUN" in Path("docs/limitations.md").read_text(encoding="utf-8")
    assert "Blend-ci" in Path("docs/gap_audit.md").read_text(encoding="utf-8")
