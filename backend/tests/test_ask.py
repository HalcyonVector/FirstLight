"""Keyword parsing and SQL building for "Ask the data" (no DB, no LLM)."""

from app.services.ask_service import clean_filter, describe, filter_sql, heuristic_filter

LANGS = ["Python", "TypeScript", "Rust", "Go", "C++", "C#", "JavaScript"]
CATS = {"databases": "Databases", "ai-agents": "AI Agents", "devtools": "Developer Tools"}


def test_language_category_and_sort():
    f = heuristic_filter("fastest-growing Rust databases", LANGS, CATS)
    assert f["language"] == "Rust"
    assert f["category"] == "databases"
    assert f["sort"] == "week"
    assert "text" not in f


def test_go_is_not_matched_inside_words():
    assert "language" not in heuristic_filter("good ai agents", LANGS, CATS)
    assert heuristic_filter("new golang cli tools", LANGS, CATS)["language"] == "Go"


def test_cpp_and_star_bounds():
    f = heuristic_filter("C++ repos under 2k stars", LANGS, CATS)
    assert f["language"] == "C++"
    assert f["max_stars"] == 2000


def test_new_and_lifecycle():
    f = heuristic_filter("brand new python projects breaking out", LANGS, CATS)
    assert f["max_age_days"] == 90
    assert f["lifecycle"] == "breakout"


def test_free_text_fallback():
    f = heuristic_filter("terminal file manager", LANGS, CATS)
    assert f["text"] == "terminal file manager"


def test_clean_filter_rejects_unknown_values():
    f = clean_filter(
        {"language": "COBOL", "category": "nope", "sort": "drop table", "limit": 500,
         "lifecycle": "zombie", "min_stars": "-5"},
        LANGS, CATS,
    )
    assert f == {"sort": "momentum", "limit": 20}


def test_filter_sql_binds_values():
    clause, params = filter_sql(
        {"language": "Rust", "category": "databases", "text": "orm", "sort": "stars", "limit": 5}
    )
    assert "Rust" not in clause and "orm" not in clause
    assert params["language"] == "Rust" and params["text"] == "orm" and params["limit"] == 5
    assert "ORDER BY r.latest_stars DESC" in clause


def test_describe_reads_back():
    text = describe({"language": "Rust", "category": "databases", "sort": "week"}, CATS)
    assert "Rust" in text and "Databases" in text and "this week" in text


def test_reasoning_opts_only_for_gpt_oss(monkeypatch):
    from app.services import ai_service

    monkeypatch.setattr(ai_service.settings, "LLM_REASONING_EFFORT", "low")
    assert ai_service.reasoning_opts("openai/gpt-oss-20b") == {"reasoning_effort": "low"}
    assert ai_service.reasoning_opts("qwen/qwen3.8-27b") == {}
    monkeypatch.setattr(ai_service.settings, "LLM_REASONING_EFFORT", "")
    assert ai_service.reasoning_opts("openai/gpt-oss-120b") == {}
