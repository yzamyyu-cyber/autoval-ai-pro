# Known Limitations

1. **Valuation-date / discount timing** — forecast cash flows use full-year discounting
   from the valuation date; a fractional fiscal-stub adjustment is not applied. Intrinsic
   value and the delayed market price are non-contemporaneous and compared as approximations.
2. **Stock splits / corporate actions** — historical weighted-average shares are taken
   as-filed; split/dilution adjustments would require a corporate-actions feed. TTM diluted
   EPS is labeled "reconstructed" and P/E is suppressed when it cannot be reconciled.
3. **CapEx gross vs net** — economic CapEx uses gross cash CapEx + finance-lease additions;
   asset-sale proceeds/incentives are not netted (they are one-off, not perpetual).
4. **Peer samples** — P/E and EV/EBITDA are assessed independently; a headline median
   requires ≥3 valid observations per metric, else "insufficient valid peers".
5. **Live data** — Yahoo Finance (yfinance) is retried with bounded backoff; failures raise
   an explicit error rather than fabricating. Saved snapshots are never presented as fresh.
6. **Provider licensing** — yfinance/Yahoo data is for personal/research use; a public
   deployment requires a licensed provider.
7. **Nonfinancial SEC filers only** — banks/insurers are out of scope.
