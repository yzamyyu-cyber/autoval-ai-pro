"""Independent numerical check: decimal arithmetic, separate from DCF engine."""
import argparse
import json
from decimal import Decimal, getcontext
from pathlib import Path
getcontext().prec = 30


def check_report(report: dict) -> dict:
    checks=[]
    for case, data in report["analysis"]["scenarios"].items():
        d=lambda v: Decimal(str(v))
        discount=d(data["wacc"])
        long_growth=d(data["terminal_growth"])
        shares=d(data["shares"])
        net_debt=d(data["net_debt_usd"])
        if isinstance(data.get("forecast_fcff_usd"), list):
            # Driver-based forecast: recompute from the supplied FCFF stream.
            stream=[Decimal(str(v)) for v in data["forecast_fcff_usd"]]
            n=len(stream)
            total=Decimal("0")
            for t, cf in enumerate(stream, start=1):
                total+=cf/(1+discount)**t
            terminal=(stream[-1]*(1+long_growth)/(discount-long_growth))/(1+discount)**n
        else:
            cf=d(data["starting_fcff_usd"])
            growth=d(data["growth"])
            n=int(data["years"])
            total=Decimal("0")
            for t in range(1,n+1):
                cash=cf*(1+growth)**t
                total+=cash/(1+discount)**t
            final=cf*(1+growth)**n
            terminal=(final*(1+long_growth)/(discount-long_growth))/(1+discount)**n
        independent=float((total+terminal-net_debt)/shares)
        actual=float(data["intrinsic_per_share_usd"])
        diff=abs(independent-actual)
        checks.append({"case":case, "independent_intrinsic_usd":round(independent,6),
                       "engine_intrinsic_usd":round(actual,6), "abs_difference_usd":diff,
                       "tolerance_usd":0.01,"pass":diff<0.01})
    order=[report["analysis"]["scenarios"][k]["intrinsic_per_share_usd"] for k in ("bear","base","bull")]
    monotone=order==sorted(order)
    return {"passed":all(c["pass"] for c in checks) and monotone,
            "independent_method":"Decimal arithmetic recomputation of forecast stream and perpetuity, not engine call",
            "scenario_order_pass":monotone,"checks":checks}


def main():
    parser=argparse.ArgumentParser(description="Independent Decimal DCF check")
    parser.add_argument("--analysis",default="outputs/demo_run/analysis.json")
    args=parser.parse_args()
    path=Path(args.analysis)
    report=json.loads(path.read_text(encoding="utf-8"))
    findings=check_report(report)
    output=path.with_name("verification.json")
    output.write_text(json.dumps(findings,indent=2),encoding="utf-8")
    print(json.dumps({"verification_path":str(output),**findings},indent=2))
    if not findings["passed"]:
        raise SystemExit(1)

if __name__=="__main__":
    main()
