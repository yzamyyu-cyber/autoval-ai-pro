"""Command-line interface for the market expectations tool."""
import argparse
import json
from pathlib import Path

from autoval.reverse import reverse_dcf


def main():
    parser = argparse.ArgumentParser(
        description="Infer the FCFF growth that matches a share price using an AutoVal analysis.",
    )
    parser.add_argument("--analysis", type=Path, required=True, help="Path to analysis.json")
    parser.add_argument("--price", type=float, help="Hypothetical price in USD per share")
    parser.add_argument("--output", type=Path, help="Optional path for the result JSON")
    args = parser.parse_args()

    try:
        report = json.loads(args.analysis.read_text(encoding="utf-8"))
        result = reverse_dcf(report, args.price)
        content = json.dumps(result, indent=2, allow_nan=False) + "\n"
        if args.output:
            args.output.write_text(content, encoding="utf-8")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        parser.error(str(exc))

    print(content, end="")


if __name__ == "__main__":
    main()
