from pathlib import Path

import pytest

from scripts.web_build_smoke import BUILD_FILES, copy_tracked_context, verify_inventory


def test_unstaged_deletion_is_skipped(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    web = tmp_path / "web"
    (web / "src").mkdir(parents=True)
    (web / "src/main.tsx").write_text("current working-tree contents", encoding="utf-8")
    context = tmp_path / "context"
    expected = copy_tracked_context(web, context, ["src/deleted.tsx", "src/main.tsx"])
    assert expected == BUILD_FILES | {"src/main.tsx"}
    assert (context / "src/main.tsx").read_text(encoding="utf-8") == "current working-tree contents"
    assert not (context / "src/deleted.tsx").exists()
    assert "Skipping deleted tracked web file: src/deleted.tsx" in capsys.readouterr().out


@pytest.mark.parametrize(
    "extra",
    [
        "test-results",
        "service-account.json",
        "id_rsa",
        "certificate.p12",
        "src/unknown.ts",
        "src/empty-directory",
    ],
)
def test_complete_inventory_rejects_unknown_entries(extra: str) -> None:
    actual = BUILD_FILES | {"src", "src/main.tsx", "node_modules", "dist", extra}
    with pytest.raises(RuntimeError, match="unexpected="):
        verify_inventory(actual, BUILD_FILES | {"src/main.tsx"})


def test_inventory_requires_declared_build_inputs() -> None:
    with pytest.raises(RuntimeError, match="missing=.*vite.config.ts"):
        verify_inventory((BUILD_FILES - {"vite.config.ts"}) | {"node_modules", "dist"}, BUILD_FILES)


def test_inventory_accepts_sources_and_generated_directories() -> None:
    verify_inventory(
        BUILD_FILES | {"src", "src/main.tsx", "node_modules", "dist"},
        BUILD_FILES | {"src/main.tsx"},
    )
