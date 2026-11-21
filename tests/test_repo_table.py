import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_repo_table as brt  # noqa: E402

TODAY = dt.date(2026, 11, 20)


def repo(name, lang="Python", pushed="2026-11-19T10:00:00Z", **kw):
    return {
        "name": name,
        "html_url": f"https://github.com/x/{name}",
        "language": lang,
        "pushed_at": pushed,
        "description": kw.get("description", "desc | with pipe"),
        "archived": kw.get("archived", False),
    }


@pytest.mark.smoke
def test_excluded_and_archived_are_dropped():
    out = brt.render(
        [repo("snk"), repo("github-profile-trophy"), repo("zz-archived-repo", archived=True), repo("agent-memory")],
        TODAY,
    )
    assert "agent-memory" in out and "snk" not in out and "zz-archived-repo" not in out
    assert "1 repositories" in out


def test_category_fallbacks_and_freshness():
    assert brt.category_key("Brand-New-A-Z") == "learning"
    assert brt.category_key("totally-new") == "other"
    assert brt.freshness("2026-11-19T00:00:00Z", TODAY) == "🟢"
    assert brt.freshness("2026-06-01T00:00:00Z", TODAY) == "🔴"


def test_pipes_escaped_and_grouping_order():
    out = brt.render([repo("EXCEL-A-Z"), repo("agent-memory"), repo("uber-driver-analytics")], TODAY)
    assert "desc / with pipe" in out
    assert out.index("uber-driver-analytics") < out.index("agent-memory") < out.index("EXCEL-A-Z")


def test_inject_replaces_only_block():
    text = f"top\n{brt.START}\nold\n{brt.END}\nbottom"
    new = brt.inject(text, "NEW")
    assert new == f"top\n{brt.START}\nNEW\n{brt.END}\nbottom"
    with pytest.raises(SystemExit):
        brt.inject("no markers", "x")
