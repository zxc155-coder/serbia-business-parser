"""Command-line entry point."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .categories import CATEGORIES, SERBIAN_CITIES
from .pipeline import by_key, run_all, run_category


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="serbia-parser",
        description="Wide-net parser for Serbian B2B businesses across 10 verticals.",
    )
    parser.add_argument(
        "--category",
        "-c",
        action="append",
        default=[],
        help="Category key (e.g. metal_detectors). Can be repeated. Default: all.",
    )
    parser.add_argument(
        "--out-dir",
        "-o",
        type=Path,
        default=Path("data"),
        help="Output directory for CSV files (one per category).",
    )
    parser.add_argument(
        "--no-maps",
        action="store_true",
        help="Skip Google Maps scraping (faster, no Selenium needed).",
    )
    parser.add_argument(
        "--cities",
        nargs="+",
        default=list(SERBIAN_CITIES),
        help="Cities to use for Google Maps queries.",
    )
    parser.add_argument(
        "--max-search",
        type=int,
        default=25,
        help="Max results per search engine query.",
    )
    parser.add_argument(
        "--max-maps",
        type=int,
        default=20,
        help="Max results per Maps query.",
    )
    parser.add_argument(
        "--max-websites",
        type=int,
        default=None,
        help="Cap on websites to crawl per category (debug/dev).",
    )
    parser.add_argument(
        "--list-categories",
        action="store_true",
        help="List available categories and exit.",
    )
    parser.add_argument("--verbose", "-v", action="count", default=0)

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING - 10 * min(args.verbose, 2),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.list_categories:
        for c in CATEGORIES:
            print(f"{c.key:25s}  {c.title_sr}  ({c.title_ru})")
        return 0

    kwargs = dict(
        use_maps=not args.no_maps,
        max_search_results=args.max_search,
        max_maps_results=args.max_maps,
        cities=args.cities,
        max_websites=args.max_websites,
    )

    if args.category:
        for key in args.category:
            try:
                cat = by_key(key)
            except KeyError:
                print(f"Unknown category: {key}", file=sys.stderr)
                return 2
            run_category(cat, args.out_dir, **kwargs)
    else:
        run_all(args.out_dir, **kwargs)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
