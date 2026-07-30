# RD14 Scored Breakout Specification V1

- Strategy ID: `AKAH_SCORED_BREAKOUT_V1`
- Strategy name: `Akah Scored Breakout V1`
- Status: `REGISTERED_FOR_RD14_CONTROLLED_VALIDATION`
- Authorization: `USER_AUTHORIZED_RD14_SCORED_STRATEGY_REGISTRATION`

## Architecture

Hard safety gates, entry opportunity score, position health score, the initial protective stop, and portfolio constraints are separate.
Entry and health scores are never shared.

## Entry

The six groups total 100 points. The frozen threshold is 70, with a 15-point breakout floor and 10-point risk/execution floor. EMA, RSI, volume, and breakout are graded components, not single vetoes.

## Exit and hysteresis

A health score at or below 20 exits at the next open. A score at or below 35 for two completed bars exits at the next open. Recovery above 35 resets confirmation. Cooldowns are three bars after a health exit and five after the hard stop. There is no absolute 30-bar exit.

## Execution and constraints

Signals use completed closes and execute at the next open. The hard stop is signal close minus two ATR14 and receives conservative gap-through treatment. Sizing risks 1% of equity, is capped at 25%, and is independent of score. Spot-only, long-only, no leverage, margin, shorts, DCA, Kelly, pyramiding, or averaging down.

No optimization or winner selection was authorized.
