# RD15 Scoring Architecture and Profit Protection Redesign

## Registered strategy

- ID: `AKAH_SCORED_BREAKOUT_V2`
- Name: Akah Scored Breakout V2
- Source commit: `f09953f23085bf241db6588d3e536c19651473c0`

## Design

RD15 separates broad entry eligibility from cross-asset ranking. It applies diminishing
returns to correlated trend/momentum evidence, penalizes overextension, and treats market
risk as a score penalty rather than a single veto.

Position management uses two independent axes: thesis health (60 points) and profit
retention health (40 points). The initial protective stop remains absolute. Once MFE reaches
1.5R, a deterministic profit floor prevents very large giveback without using pyramiding,
shorting, leverage, margin, DCA, Kelly, or averaging down.
