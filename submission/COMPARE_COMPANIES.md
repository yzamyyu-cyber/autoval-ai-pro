# Compare Companies

Select **Compare Companies** in the AutoVal workspace. **Bundled examples** opens two
synthetic valuations directly. **Saved analysis files** accepts two AutoVal Analysis JSON
exports. Both workflows run locally without fetching market prices or SEC filings.

The table and CSV include the base DCF per share, price and reporting dates, valuation
gap, WACC, forecast growth and its measure, price-implied FCFF growth, and peer medians
when available. Figures in the table are rounded. The CSV keeps numerical precision
and represents unavailable fields as blank. The table flags mismatched data modes,
currencies, dates, and growth or WACC bases.

## Run on macOS

From the full source folder, run these in Terminal:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

Open [http://127.0.0.1:8501](http://127.0.0.1:8501) in the browser on that Mac and keep
Terminal open. Select **Compare Companies** and use **Download comparison CSV**.

## Offline reproduction

```bash
.venv/bin/python run_analysis.py --mode demo --ticker DEMO --output outputs/demo_run
.venv/bin/python run_analysis.py --mode demo --ticker DEMO2 --output outputs/demo2_run
.venv/bin/python -m unittest discover -s tests -q
```

You can drag the two resulting `analysis.json` files into **Saved analysis files**. The
bundled examples give the same modeled values and require no pre-generated output files.

| Synthetic company | Reference price | Base DCF per share | Valuation gap |
|---|---:|---:|---:|
| DEMO | $145.00 | $139.85 | −3.55% |
| DEMO2 | $82.50 | $95.01 | +15.16% |

For DEMO, the unrounded base value is approximately $139.845349. The gap is
`(139.845349 / 145.00 − 1) × 100`, about −3.5549%. The display rounds to −3.55%.
This check measures arithmetic and export consistency.
