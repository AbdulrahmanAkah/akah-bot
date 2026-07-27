# AMS RD01-D0 — Dominance Data and Causality Validation

## Executive result

- Status: `BLOCKED_BY_DATA`
- Reason: `UPSTREAM_HISTORY_UNAVAILABLE`
- Research stage: `RD01-D0`
- Scope: data ingestion and causality validation only
- Trading decisions changed: `NO`
- Overlay authorized: `NO`
- ATI-V1 authorized: `NO`

## Blocker

HTTP 400 from https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=%2A&metrics=CapMrktCurUSD&start_time=2021-01-01T00%3A00%3A00%2B00%3A00&end_time=2024-12-31T00%3A00%3A00%2B00%3A00&frequency=1d&page_size=10000&paging_from=start&ignore_forbidden_errors=true&ignore_unsupported_errors=true: {"error":{"type":"bad_parameter","message":"Bad parameter 'start_time'. Incorrect time format '2021-01-01T00:00:00+00:00'. Supported formats are 'yyyy-MM-dd', 'yyyyMMdd', 'yyyy-MM-ddTHH:mm:ss', 'yyyy-MM-ddTHHmmss', 'yyyy-MM-ddTHH:mm:ss.SSS', 'yyyy-MM-ddTHHmmss.SSS', 'yyyy-MM-ddTHH:mm:ss.SSSSSS', 'yyyy-MM-ddTHHmmss.SSSSSS', 'yyyy-MM-ddTHH:mm:ss.SSSSSSSSS', 'yyyy-MM-ddTHHmmss.SSSSSSSSS'."}}

## Safety boundaries

- No 2025 test data access.
- No 2026 holdout access.
- No M05 entry, exit, sizing, or ranking change.
- No production, live trading, MD02, Kelly, or leverage authorization.
