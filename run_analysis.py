"""CLI for WorkSwarm and grading evidence."""
import argparse
import os
import json
from autoval.pipeline import build_analysis, save_analysis


def main():
    parser = argparse.ArgumentParser(description="Automatic educational equity research")
    parser.add_argument("--ticker", default="DEMO")
    parser.add_argument("--mode", choices=["demo", "live"], default="demo")
    parser.add_argument("--output", default="outputs/demo_run")
    args = parser.parse_args()
    result, frame = build_analysis(args.ticker, args.mode, os.environ.get("SEC_USER_AGENT", ""))
    files = save_analysis(result, frame, args.output)
    print(json.dumps({"ticker":result["ticker"], "mode":args.mode,
                      "market_price":result["analysis"]["market_price"],
                      "scenarios":{k:round(v["intrinsic_per_share_usd"],2)
                                   for k,v in result["analysis"]["scenarios"].items()},
                      "saved_files":files}, indent=2))


if __name__ == "__main__":
    main()
