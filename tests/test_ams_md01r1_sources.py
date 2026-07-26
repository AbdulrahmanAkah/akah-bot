from __future__ import annotations

from spotbot.research.ams_md01r1_universe import extract_usdt_bases


def test_official_announcement_pair_extraction_is_conservative() -> None:
    text = "Trading pairs ABC/USDT and XYZ-USDT; futures OTHERUSDT."
    assert extract_usdt_bases(text) == ("ABC", "OTHER", "XYZ")


def test_unrelated_parenthetical_text_is_not_a_pair_candidate() -> None:
    assert extract_usdt_bases("Maintenance notice (UTC)") == ()
