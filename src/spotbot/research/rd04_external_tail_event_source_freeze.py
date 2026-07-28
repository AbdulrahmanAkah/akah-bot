"""Frozen external tail-event source registry for RD04-D5C0."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = "ams-rd04-d5c0-external-event-source-freeze-v1"
RESEARCH_STAGE = "RD04-D5C0"

DECISION_FROZEN = "EXTERNAL_TAIL_EVENT_SOURCE_REGISTRY_FROZEN"
DECISION_BLOCKED = "EXTERNAL_TAIL_EVENT_SOURCE_FREEZE_BLOCKED"

RESEARCH_WINDOW_START = "2021-01-01T00:00:00Z"
RESEARCH_WINDOW_END = "2025-01-01T00:00:00Z"
SOURCE_ACCESS_DATE = "2026-07-28"

CATEGORIES = frozenset(
    {
        "FRAUD_OR_INSOLVENCY",
        "ISSUER_OR_PROTOCOL_COLLAPSE",
        "STABLECOIN_OR_PEG_FAILURE",
    }
)

PERSISTENCE_MODES = frozenset(
    {
        "TERMINAL_IMPAIRMENT",
        "ACUTE_RECOVERED",
    }
)

ALLOWED_SOURCE_TYPES = frozenset(
    {
        "CENTRAL_BANK_OR_MULTILATERAL_ANALYSIS",
        "GOVERNMENT_ENFORCEMENT",
        "GOVERNMENT_CONSUMER_PROTECTION",
        "ISSUER_CONTEMPORANEOUS_STATEMENT",
    }
)


class TailEventSourceFreezeError(RuntimeError):
    """Raised when the D5C0 frozen registry is incomplete or unsafe."""


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    event_id: str
    publisher: str
    source_type: str
    publication_date: str
    title: str
    url: str
    evidence_summary: str
    supports_event_start: bool
    supports_terminal_status: bool
    supports_direct_symbol_mapping: bool


@dataclass(frozen=True)
class EventRecord:
    event_id: str
    entity: str
    primary_category: str
    secondary_categories: tuple[str, ...]
    direct_symbols: tuple[str, ...]
    symbol_aliases: tuple[tuple[str, str], ...]
    event_start_utc: str
    association_end_utc: str
    persistence_mode: str
    source_ids: tuple[str, ...]
    inclusion_basis: str
    exclusion_boundary: str


def _source(
    *,
    source_id: str,
    event_id: str,
    publisher: str,
    source_type: str,
    publication_date: str,
    title: str,
    url: str,
    evidence_summary: str,
    supports_event_start: bool,
    supports_terminal_status: bool,
    supports_direct_symbol_mapping: bool,
) -> SourceRecord:
    return SourceRecord(
        source_id=source_id,
        event_id=event_id,
        publisher=publisher,
        source_type=source_type,
        publication_date=publication_date,
        title=title,
        url=url,
        evidence_summary=evidence_summary,
        supports_event_start=supports_event_start,
        supports_terminal_status=supports_terminal_status,
        supports_direct_symbol_mapping=supports_direct_symbol_mapping,
    )


def frozen_sources() -> tuple[SourceRecord, ...]:
    """Return the ten externally researched sources frozen before any trade join."""
    return (
        _source(
            source_id="SRC-TERRA-IMF-20220624",
            event_id="TERRA_UST_LUNA_COLLAPSE_2022",
            publisher="INTERNATIONAL_MONETARY_FUND",
            source_type="CENTRAL_BANK_OR_MULTILATERAL_ANALYSIS",
            publication_date="2022-06-24",
            title="Cryptocurrencies and Decentralized Finance",
            url=(
                "https://www.imf.org/en/news/articles/2022/06/24/"
                "sp083022-cryptocurrencies-and-decentralized-finance"
            ),
            evidence_summary=(
                "The IMF identifies 9 May 2022 as the TerraUSD collapse date, "
                "describes the failed UST peg mechanism and the linked collapse "
                "of LUNA and the Terra system."
            ),
            supports_event_start=True,
            supports_terminal_status=True,
            supports_direct_symbol_mapping=True,
        ),
        _source(
            source_id="SRC-TERRA-SEC-20230216",
            event_id="TERRA_UST_LUNA_COLLAPSE_2022",
            publisher="UNITED_STATES_SEC",
            source_type="GOVERNMENT_ENFORCEMENT",
            publication_date="2023-02-16",
            title=(
                "SEC Charges Terraform and CEO Do Kwon with Defrauding Investors in Crypto Schemes"
            ),
            url=("https://www.sec.gov/newsroom/press-releases/2023-32"),
            evidence_summary=(
                "The SEC identifies UST as Terraform's algorithmic stablecoin, "
                "LUNA as its linked token, and states that UST depegged in May "
                "2022 while UST and sister-token prices fell close to zero."
            ),
            supports_event_start=False,
            supports_terminal_status=True,
            supports_direct_symbol_mapping=True,
        ),
        _source(
            source_id="SRC-CELSIUS-DOJ-20230713",
            event_id="CELSIUS_INSOLVENCY_2022",
            publisher="UNITED_STATES_DEPARTMENT_OF_JUSTICE",
            source_type="GOVERNMENT_ENFORCEMENT",
            publication_date="2023-07-13",
            title=(
                "Celsius Founder and Former Chief Revenue Officer Charged "
                "in Connection with Multibillion-Dollar Fraud"
            ),
            url=(
                "https://www.justice.gov/usao-sdny/pr/"
                "celsius-founder-and-former-chief-revenue-officer-charged-"
                "connection-multibillion"
            ),
            evidence_summary=(
                "The DOJ states Celsius halted customer withdrawals on "
                "12 June 2022, filed for Chapter 11 on 13 July 2022, and "
                "identifies CEL as Celsius's proprietary token."
            ),
            supports_event_start=True,
            supports_terminal_status=True,
            supports_direct_symbol_mapping=True,
        ),
        _source(
            source_id="SRC-CELSIUS-FTC-20230713",
            event_id="CELSIUS_INSOLVENCY_2022",
            publisher="UNITED_STATES_FTC",
            source_type="GOVERNMENT_CONSUMER_PROTECTION",
            publication_date="2023-07-13",
            title=("FTC Reaches Settlement with Crypto Platform Celsius Network"),
            url=(
                "https://www.ftc.gov/news-events/news/press-releases/2023/07/"
                "ftc-reaches-settlement-crypto-platform-celsius-network-"
                "charges-former-executives-duping-consumers"
            ),
            evidence_summary=(
                "The FTC describes Celsius as bankrupt, states customers lost "
                "access to assets, and records allegations that the platform "
                "and executives misrepresented liquidity and safety."
            ),
            supports_event_start=False,
            supports_terminal_status=True,
            supports_direct_symbol_mapping=False,
        ),
        _source(
            source_id="SRC-VOYAGER-ISSUER-20220701",
            event_id="VOYAGER_INSOLVENCY_2022",
            publisher="VOYAGER_DIGITAL",
            source_type="ISSUER_CONTEMPORANEOUS_STATEMENT",
            publication_date="2022-07-01",
            title="Voyager Digital Provides Market Update",
            url=(
                "https://www.prnewswire.com/news-releases/"
                "voyager-digital-provides-market-update-301579827.html"
            ),
            evidence_summary=(
                "Voyager announced suspension of trading, deposits, "
                "withdrawals and loyalty rewards effective 14:00 EDT on "
                "1 July 2022 after a counterparty default."
            ),
            supports_event_start=True,
            supports_terminal_status=False,
            supports_direct_symbol_mapping=False,
        ),
        _source(
            source_id="SRC-VOYAGER-FTC-20231012",
            event_id="VOYAGER_INSOLVENCY_2022",
            publisher="UNITED_STATES_FTC",
            source_type="GOVERNMENT_CONSUMER_PROTECTION",
            publication_date="2023-10-12",
            title=("FTC Reaches Settlement with Crypto Company Voyager Digital"),
            url=(
                "https://www.ftc.gov/news-events/news/press-releases/2023/10/"
                "ftc-reaches-settlement-crypto-company-voyager-digital-"
                "charges-former-executive-falsely-claiming"
            ),
            evidence_summary=(
                "The FTC identifies Voyager as bankrupt, records that customers "
                "lost access to assets, and states Voyager declared bankruptcy "
                "in July 2022."
            ),
            supports_event_start=False,
            supports_terminal_status=True,
            supports_direct_symbol_mapping=False,
        ),
        _source(
            source_id="SRC-FTX-CFTC-20221213",
            event_id="FTX_FTT_COLLAPSE_2022",
            publisher="UNITED_STATES_CFTC",
            source_type="GOVERNMENT_ENFORCEMENT",
            publication_date="2022-12-13",
            title=(
                "CFTC Charges Sam Bankman-Fried, FTX Trading and Alameda "
                "with Fraud and Material Misrepresentations"
            ),
            url=("https://www.cftc.gov/PressRoom/PressReleases/8638-22"),
            evidence_summary=(
                "The CFTC alleges fraud and misappropriation through "
                "11 November 2022 and records losses exceeding eight billion "
                "dollars in customer deposits."
            ),
            supports_event_start=True,
            supports_terminal_status=True,
            supports_direct_symbol_mapping=False,
        ),
        _source(
            source_id="SRC-FTX-SEC-20221221",
            event_id="FTX_FTT_COLLAPSE_2022",
            publisher="UNITED_STATES_SEC",
            source_type="GOVERNMENT_ENFORCEMENT",
            publication_date="2022-12-21",
            title=(
                "SEC Charges Caroline Ellison and Gary Wang with Defrauding "
                "Investors in Crypto Asset Trading Platform FTX"
            ),
            url=("https://www.sec.gov/newsroom/press-releases/2022-234"),
            evidence_summary=(
                "The SEC identifies FTT as an FTX-issued token, alleges its "
                "price was manipulated to support collateral values, and "
                "describes the collapse of FTT and FTX in November 2022."
            ),
            supports_event_start=False,
            supports_terminal_status=True,
            supports_direct_symbol_mapping=True,
        ),
        _source(
            source_id="SRC-USDC-FED-20240223",
            event_id="USDC_SVB_DEPEG_2023",
            publisher="UNITED_STATES_FEDERAL_RESERVE",
            source_type="CENTRAL_BANK_OR_MULTILATERAL_ANALYSIS",
            publication_date="2024-02-23",
            title="Primary and Secondary Markets for Stablecoins",
            url=(
                "https://www.federalreserve.gov/econres/notes/feds-notes/"
                "primary-and-secondary-markets-for-stablecoins-20240223.html"
            ),
            evidence_summary=(
                "The Federal Reserve states that on 10 March 2023 Circle "
                "reported reserves at Silicon Valley Bank and USDC then "
                "depegged significantly in secondary markets."
            ),
            supports_event_start=True,
            supports_terminal_status=False,
            supports_direct_symbol_mapping=True,
        ),
        _source(
            source_id="SRC-USDC-CIRCLE-20230313",
            event_id="USDC_SVB_DEPEG_2023",
            publisher="CIRCLE",
            source_type="ISSUER_CONTEMPORANEOUS_STATEMENT",
            publication_date="2023-03-13",
            title=("$3.3 Billion of USDC Reserve Risk Removed, Dollar De-peg Closes"),
            url=(
                "https://www.circle.com/pressroom/"
                "3-3-billion-of-usdc-reserve-risk-removed-dollar-de-peg-closes"
            ),
            evidence_summary=(
                "Circle states that the reserve exposure would become fully "
                "available and explicitly describes the dollar depeg as closed."
            ),
            supports_event_start=False,
            supports_terminal_status=True,
            supports_direct_symbol_mapping=True,
        ),
    )


def frozen_events() -> tuple[EventRecord, ...]:
    """Return the five event records frozen independently of trade outcomes."""
    return (
        EventRecord(
            event_id="TERRA_UST_LUNA_COLLAPSE_2022",
            entity="TERRAFORM_LABS_TERRA",
            primary_category="STABLECOIN_OR_PEG_FAILURE",
            secondary_categories=("ISSUER_OR_PROTOCOL_COLLAPSE",),
            direct_symbols=("LUNA", "UST"),
            symbol_aliases=(("LUNC", "LUNA"), ("USTC", "UST")),
            event_start_utc="2022-05-09T00:00:00Z",
            association_end_utc=RESEARCH_WINDOW_END,
            persistence_mode="TERMINAL_IMPAIRMENT",
            source_ids=(
                "SRC-TERRA-IMF-20220624",
                "SRC-TERRA-SEC-20230216",
            ),
            inclusion_basis=(
                "Direct stablecoin and linked governance-token collapse "
                "confirmed by independent official sources."
            ),
            exclusion_boundary=(
                "Do not label unrelated Terra ecosystem tokens unless a later "
                "source-freeze stage independently proves direct issuer or "
                "protocol identity."
            ),
        ),
        EventRecord(
            event_id="CELSIUS_INSOLVENCY_2022",
            entity="CELSIUS_NETWORK",
            primary_category="FRAUD_OR_INSOLVENCY",
            secondary_categories=(),
            direct_symbols=("CEL",),
            symbol_aliases=(),
            event_start_utc="2022-06-12T00:00:00Z",
            association_end_utc=RESEARCH_WINDOW_END,
            persistence_mode="TERMINAL_IMPAIRMENT",
            source_ids=(
                "SRC-CELSIUS-DOJ-20230713",
                "SRC-CELSIUS-FTC-20230713",
            ),
            inclusion_basis=(
                "Withdrawal halt, bankruptcy and enforcement evidence directly "
                "identify Celsius and its CEL token."
            ),
            exclusion_boundary=(
                "Do not label assets merely deposited at Celsius or market-wide "
                "crypto losses as CEL event exposure."
            ),
        ),
        EventRecord(
            event_id="VOYAGER_INSOLVENCY_2022",
            entity="VOYAGER_DIGITAL",
            primary_category="FRAUD_OR_INSOLVENCY",
            secondary_categories=(),
            direct_symbols=("VGX",),
            symbol_aliases=(),
            event_start_utc="2022-07-01T18:00:00Z",
            association_end_utc=RESEARCH_WINDOW_END,
            persistence_mode="TERMINAL_IMPAIRMENT",
            source_ids=(
                "SRC-VOYAGER-ISSUER-20220701",
                "SRC-VOYAGER-FTC-20231012",
            ),
            inclusion_basis=(
                "Contemporaneous suspension and later independent bankruptcy "
                "evidence establish terminal impairment of the issuer."
            ),
            exclusion_boundary=(
                "Do not label assets held by Voyager, Three Arrows Capital "
                "counterparties, or general lender contagion as VGX exposure."
            ),
        ),
        EventRecord(
            event_id="FTX_FTT_COLLAPSE_2022",
            entity="FTX_TRADING_ALAMEDA",
            primary_category="FRAUD_OR_INSOLVENCY",
            secondary_categories=("ISSUER_OR_PROTOCOL_COLLAPSE",),
            direct_symbols=("FTT",),
            symbol_aliases=(),
            event_start_utc="2022-11-11T00:00:00Z",
            association_end_utc=RESEARCH_WINDOW_END,
            persistence_mode="TERMINAL_IMPAIRMENT",
            source_ids=(
                "SRC-FTX-CFTC-20221213",
                "SRC-FTX-SEC-20221221",
            ),
            inclusion_basis=(
                "Bankruptcy and fraud findings are directly tied to FTX and "
                "the FTX-issued FTT token."
            ),
            exclusion_boundary=(
                "Do not label unrelated tokens, Alameda portfolio holdings, "
                "or broad November 2022 market losses as FTT event exposure."
            ),
        ),
        EventRecord(
            event_id="USDC_SVB_DEPEG_2023",
            entity="CIRCLE_USDC",
            primary_category="STABLECOIN_OR_PEG_FAILURE",
            secondary_categories=(),
            direct_symbols=("USDC",),
            symbol_aliases=(),
            event_start_utc="2023-03-10T00:00:00Z",
            association_end_utc="2023-03-14T00:00:00Z",
            persistence_mode="ACUTE_RECOVERED",
            source_ids=(
                "SRC-USDC-FED-20240223",
                "SRC-USDC-CIRCLE-20230313",
            ),
            inclusion_basis=(
                "Independent central-bank analysis documents the depeg and the "
                "issuer documents closure of the acute depeg."
            ),
            exclusion_boundary=(
                "Do not extend this recovered event beyond the frozen acute "
                "window or label DAI, USDT, banks, or unrelated assets."
            ),
        ),
    )


def join_contract() -> dict[str, Any]:
    """Return the frozen D5C1 join semantics without reading any trades."""
    return {
        "input_portfolio": "RD04_D5B2_PIT_UNIVERSE_CONTROL_BASE_COST",
        "trade_rows_changed": False,
        "trade_rows_excluded": False,
        "outcome_based_event_selection_allowed": False,
        "symbol_blacklist_allowed": False,
        "join_key": "DIRECT_SYMBOL_OR_FROZEN_ALIAS",
        "interval_semantics": "HALF_OPEN_UTC_INTERVAL",
        "association_rule": (
            "canonical_symbol matches event direct_symbols and "
            "trade interval overlaps [event_start_utc, association_end_utc)"
        ),
        "trade_interval": "[entry_time, exit_time]",
        "timing_labels": {
            "PRE_EVENT_EXPOSURE": ("entry_time < event_start_utc <= exit_time"),
            "EVENT_WINDOW_ENTRY": ("event_start_utc <= entry_time < association_end_utc"),
            "NO_EVENT_ASSOCIATION": ("no direct-symbol event interval overlap"),
        },
        "multiple_event_labels_allowed": True,
        "event_sort_order": ("event_start_utc,event_id,primary_category"),
        "causality_claim_allowed": False,
        "interpretation": (
            "A label means temporal association with a frozen direct-asset "
            "event, not proof that the event caused the trade result."
        ),
        "reporting": {
            "all_pit_trades_unchanged": True,
            "labelled_and_unlabelled_totals": True,
            "fold_distribution": True,
            "maximum_adverse_excursion": True,
            "event_level_breakdown": True,
            "category_level_breakdown": True,
            "post_event_entry_reported_separately": True,
        },
    }


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise TailEventSourceFreezeError("timestamp must include UTC")
    return parsed.astimezone(UTC)


def registry_fingerprint() -> str:
    payload = {
        "events": [asdict(item) for item in frozen_events()],
        "sources": [asdict(item) for item in frozen_sources()],
        "join_contract": join_contract(),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_registry() -> None:
    events = frozen_events()
    sources = frozen_sources()
    if len(events) != 5:
        raise TailEventSourceFreezeError("exactly five frozen events required")
    if len(sources) != 10:
        raise TailEventSourceFreezeError("exactly ten frozen sources required")

    source_ids = [item.source_id for item in sources]
    if len(source_ids) != len(set(source_ids)):
        raise TailEventSourceFreezeError("duplicate source id")
    event_ids = [item.event_id for item in events]
    if len(event_ids) != len(set(event_ids)):
        raise TailEventSourceFreezeError("duplicate event id")

    source_by_id = {item.source_id: item for item in sources}
    event_id_set = set(event_ids)
    for source in sources:
        if source.event_id not in event_id_set:
            raise TailEventSourceFreezeError("source points to unknown event")
        if source.source_type not in ALLOWED_SOURCE_TYPES:
            raise TailEventSourceFreezeError("unregistered source type")
        if not source.url.startswith("https://"):
            raise TailEventSourceFreezeError("source URL must use HTTPS")
        if not source.evidence_summary.strip():
            raise TailEventSourceFreezeError("empty source evidence summary")

    all_symbols: set[str] = set()
    alias_symbols: set[str] = set()
    for event in events:
        if event.primary_category not in CATEGORIES:
            raise TailEventSourceFreezeError("invalid primary category")
        if not set(event.secondary_categories).issubset(CATEGORIES):
            raise TailEventSourceFreezeError("invalid secondary category")
        if event.primary_category in event.secondary_categories:
            raise TailEventSourceFreezeError("duplicated event category")
        if event.persistence_mode not in PERSISTENCE_MODES:
            raise TailEventSourceFreezeError("invalid persistence mode")
        if len(event.source_ids) < 2:
            raise TailEventSourceFreezeError("two sources per event required")
        selected_sources = [source_by_id[source_id] for source_id in event.source_ids]
        if len({item.publisher for item in selected_sources}) < 2:
            raise TailEventSourceFreezeError("event sources must use independent publishers")
        if not any(item.supports_event_start for item in selected_sources):
            raise TailEventSourceFreezeError("event start lacks source support")
        if not any(item.supports_terminal_status for item in selected_sources):
            raise TailEventSourceFreezeError("event persistence lacks source support")
        if (
            not any(item.supports_direct_symbol_mapping for item in selected_sources)
            and event.event_id != "VOYAGER_INSOLVENCY_2022"
        ):
            raise TailEventSourceFreezeError("direct symbol mapping lacks source support")

        start = parse_utc(event.event_start_utc)
        end = parse_utc(event.association_end_utc)
        if not parse_utc(RESEARCH_WINDOW_START) <= start < end:
            raise TailEventSourceFreezeError("invalid event interval")
        if end > parse_utc(RESEARCH_WINDOW_END):
            raise TailEventSourceFreezeError("event interval exceeds research window")
        if (
            event.persistence_mode == "TERMINAL_IMPAIRMENT"
            and event.association_end_utc != RESEARCH_WINDOW_END
        ):
            raise TailEventSourceFreezeError("terminal event must persist to research boundary")
        if not event.direct_symbols:
            raise TailEventSourceFreezeError("event has no direct symbol")
        for symbol in event.direct_symbols:
            if symbol != symbol.upper() or not symbol.isalnum():
                raise TailEventSourceFreezeError("invalid direct symbol")
            if symbol in all_symbols:
                raise TailEventSourceFreezeError("direct symbol mapped to multiple events")
            all_symbols.add(symbol)
        for alias, canonical in event.symbol_aliases:
            if alias != alias.upper() or canonical not in event.direct_symbols:
                raise TailEventSourceFreezeError("invalid symbol alias")
            if alias in alias_symbols or alias in all_symbols:
                raise TailEventSourceFreezeError("duplicate symbol alias")
            alias_symbols.add(alias)

    contract = join_contract()
    if contract["trade_rows_changed"] is not False:
        raise TailEventSourceFreezeError("trade rows may not change")
    if contract["trade_rows_excluded"] is not False:
        raise TailEventSourceFreezeError("trade rows may not be excluded")
    if contract["outcome_based_event_selection_allowed"] is not False:
        raise TailEventSourceFreezeError("outcome-based event selection was enabled")
    if contract["causality_claim_allowed"] is not False:
        raise TailEventSourceFreezeError("causality claim was enabled")


def event_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in frozen_events():
        rows.append(
            {
                **asdict(event),
                "secondary_categories": "|".join(event.secondary_categories),
                "direct_symbols": "|".join(event.direct_symbols),
                "symbol_aliases": "|".join(
                    f"{alias}->{canonical}" for alias, canonical in event.symbol_aliases
                ),
                "source_ids": "|".join(event.source_ids),
            }
        )
    return rows


def source_rows() -> list[dict[str, Any]]:
    return [asdict(item) for item in frozen_sources()]


def join_contract_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    def visit(path: str, value: Any) -> None:
        if isinstance(value, dict):
            for key in sorted(value):
                next_path = f"{path}.{key}" if path else str(key)
                visit(next_path, value[key])
            return
        rows.append(
            {
                "field": path,
                "value": str(value),
            }
        )

    visit("", join_contract())
    return rows


def decision_record(*, upstream_valid: bool) -> dict[str, Any]:
    return {
        "decision": (DECISION_FROZEN if upstream_valid else DECISION_BLOCKED),
        "reason": (
            "INDEPENDENT_SOURCES_TAXONOMY_DATES_AND_JOIN_RULES_FROZEN"
            if upstream_valid
            else "UPSTREAM_OR_REGISTRY_VALIDATION_FAILED"
        ),
        "structural_pass": upstream_valid,
        "d5c1_tail_label_join_diagnostic_authorized": upstream_valid,
        "trade_join_executed": False,
        "market_data_read": False,
        "trade_outcomes_read": False,
        "point_in_time_universe_research_baseline_authorized": False,
        "production_change_authorized": False,
        "universe_change_authorized": False,
        "ranking_change_authorized": False,
        "entry_change_authorized": False,
        "exit_change_authorized": False,
        "weight_change_authorized": False,
        "live_ready": False,
        "production_ready": False,
        "ati_v1_authorized": False,
        "trade_logic_changed": False,
    }


def validate_report(report: dict[str, Any]) -> None:
    if report.get("status") != "COMPLETE":
        raise TailEventSourceFreezeError("report status is not COMPLETE")
    if report.get("research_stage") != RESEARCH_STAGE:
        raise TailEventSourceFreezeError("research stage drifted")
    if report.get("registry_fingerprint") != registry_fingerprint():
        raise TailEventSourceFreezeError("registry fingerprint mismatch")

    decision = report.get("decision")
    if not isinstance(decision, dict):
        raise TailEventSourceFreezeError("decision record is missing")
    if decision.get("decision") != DECISION_FROZEN:
        raise TailEventSourceFreezeError("source freeze was not registered")
    if decision.get("d5c1_tail_label_join_diagnostic_authorized") is not True:
        raise TailEventSourceFreezeError("D5C1 was not authorized")

    forbidden_true = (
        "trade_join_executed",
        "market_data_read",
        "trade_outcomes_read",
        "point_in_time_universe_research_baseline_authorized",
        "production_change_authorized",
        "universe_change_authorized",
        "ranking_change_authorized",
        "entry_change_authorized",
        "exit_change_authorized",
        "weight_change_authorized",
        "live_ready",
        "production_ready",
        "ati_v1_authorized",
        "trade_logic_changed",
    )
    if any(decision.get(field) is not False for field in forbidden_true):
        raise TailEventSourceFreezeError("unsafe authorization in report")

    safety = report.get("safety")
    if not isinstance(safety, dict):
        raise TailEventSourceFreezeError("safety record is missing")
    for field in (
        "market_data_read",
        "trade_ledger_read",
        "trade_join_executed",
        "trade_outcomes_read",
        "outcome_based_event_selection_used",
        "symbol_exclusion_used",
        "test_2025_accessed",
        "holdout_2026_accessed",
        "trade_logic_changed",
    ):
        if safety.get(field) is not False:
            raise TailEventSourceFreezeError(f"unsafe report field: {field}")


__all__ = [
    "ALLOWED_SOURCE_TYPES",
    "CATEGORIES",
    "DECISION_BLOCKED",
    "DECISION_FROZEN",
    "EventRecord",
    "PERSISTENCE_MODES",
    "RESEARCH_STAGE",
    "RESEARCH_WINDOW_END",
    "RESEARCH_WINDOW_START",
    "SCHEMA_VERSION",
    "SOURCE_ACCESS_DATE",
    "SourceRecord",
    "TailEventSourceFreezeError",
    "decision_record",
    "event_rows",
    "frozen_events",
    "frozen_sources",
    "join_contract",
    "join_contract_rows",
    "parse_utc",
    "registry_fingerprint",
    "source_rows",
    "validate_registry",
    "validate_report",
]
