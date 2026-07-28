from spotbot.research.rd07_binance_source import ArchiveRequest, parse_checksum


def test_archive_url_is_spot_monthly_4h() -> None:
    request = ArchiveRequest("BTC", "BTCUSDT", "2024-12")
    assert "/spot/monthly/klines/BTCUSDT/4h/" in request.url
    assert request.filename == "BTCUSDT-4h-2024-12.zip"


def test_checksum_parser() -> None:
    value = "a" * 64
    assert parse_checksum(f"{value}  file.zip\n") == value
