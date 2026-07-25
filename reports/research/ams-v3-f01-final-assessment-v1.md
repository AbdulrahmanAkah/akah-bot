# AMS V3 F01 final assessment

- Assessment: `FAIL`
- Is the strategy successful? No; the registered family fails the paired Fibonacci test.
- Did Fibonacci add value? No. C02 made zero trades versus C01's 67.
- Best configuration: `AMS-V3-F01-C14` on `AMS-V3-PORTFOLIO-P02`.
- Worst C01 fold return: -2.18%.
- Does C01 tolerate 0.4% fees? Yes mechanically: 32.10%; Fibonacci does not trade.
- Is trade count sufficient? C01 has 67 trades; C02 has none, so the paired Fibonacci result rejects this filter implementation.
- Largest weakness: the Fibonacci filter eliminates every eligible entry under the frozen setup semantics.
- Open 2025 later? No. First preregister a redesigned filter and wire the portfolio profile dimension into runtime behavior.
- Next scientific step: run a new, separately registered protocol after that redesign; do not modify this completed trial set.

## Paired results

| Trial | Base compounded return | Stress return | Trades |
| --- | ---: | ---: | ---: |
| C01 control | 33.96% | 32.10% | 67 |
| C02 Fibonacci | 0.00% | 0.00% | 0 |
