# RD18-P2U methodology

RD18-P2U is an offline confidence-aware design stage for the restricted KuCoin Spot panel. The frozen design uses the committed C ranking, two adjacent boundary checks (6/7 then 8/9), and a maximum ten-percent relative liquidity gap. It permits at most one adjacent swap at each boundary and does not construct an intersection or globally reorder assets.

The input audit found that all twelve products classified by RD18-P2T as leveraged or synthetic are present in the committed P1R C ranking. The stage therefore stops before Variant E construction. No previous artifact is repaired or rewritten, and no market-data request is made.

The valid claim remains `RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS`; it is not an exhaustive KuCoin inventory claim.
