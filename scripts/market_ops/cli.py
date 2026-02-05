import argparse
import json


def main():
    ap = argparse.ArgumentParser(prog="market_ops")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--cache-ttl", default="")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("symbol")
    s.add_argument("symbol")
    s.add_argument("--template", default="dashboard", choices=["dashboard", "plan"])
    s.add_argument("--no-llm", action="store_true")

    c = sub.add_parser("ca")
    c.add_argument("address")
    c.add_argument("--no-llm", action="store_true")

    h = sub.add_parser("hourly")
    h.add_argument("--budget", type=float, default=240.0)

    args = ap.parse_args()

    from .facade import analyze_ca_facade, analyze_hourly, analyze_symbol_facade

    if args.cmd == "symbol":
        out = analyze_symbol_facade(args.symbol, template=args.template, allow_llm=not args.no_llm)
    elif args.cmd == "ca":
        out = analyze_ca_facade(args.address, allow_llm=not args.no_llm)
    else:
        out = analyze_hourly(total_budget_s=args.budget, fresh=args.fresh, cache_ttl=args.cache_ttl)

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
