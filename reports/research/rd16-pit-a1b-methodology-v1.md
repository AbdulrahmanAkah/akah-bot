# RD16-PIT-A1B Methodology

A1B addresses the unresolved 2019-2020 market-cap membership identified by A1.

The stage queries only the Coin Metrics Community
`/v4/timeseries/asset-metrics` endpoint. Requests are hard bounded from
2018-12-30 through 2020-12-31 and use daily `CapMrktCurUSD` and
`CapMrktEstUSD` observations. No catalog endpoint is queried because current
catalog metadata is unnecessary for this historical audit.

Every generated URL is validated before transmission. Only HTTPS requests to
`community-api.coinmetrics.io` are permitted. Any URL containing 2025 or 2026,
a changed endpoint, or changed date boundaries is rejected.

For each asset-day, current market capitalization is preferred; estimated
market capitalization is used only when current capitalization is unavailable.
The resulting panel is stored as a frozen Parquet artifact with a SHA-256
digest.

Stablecoins, cash representations, wrapped assets, and network-specific
duplicate representations are excluded through the existing A1 normalization.
Monday rankings use only Sunday observations through the established one-day
information lag.

A historical week is considered rank-resolved only when at least 30 eligible
assets are present after exclusions. Incomplete weekly snapshots remain
unresolved rather than producing ranks from a truncated universe.

A1B then repeats the ledger-level attribution and bounded scenarios for the
registered 567-trade V3 ledger. This still does not replay portfolio routing,
cash, drawdown, concurrent risk, or position admission.

Moving-block bootstrap and effective sample size remain descriptive only.
No bootstrap p-value or Benjamini-Hochberg confirmation gate is authorized.
RD16-U remains stopped.
