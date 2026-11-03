import os
import glob
import yaml
import argparse
import webbrowser
from datetime import datetime

from core.engine import PipelineEngine
from core.utils import log, clear_low_scores

def load_recipe(recipe_path: str) -> dict:
    if not os.path.exists(recipe_path):
        raise FileNotFoundError(f"Recipe file not found: {recipe_path}")
    with open(recipe_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def clean_locks(out_dir: str = "output"):
    for f in glob.glob("*.lock") + glob.glob(os.path.join(out_dir, "*.lock")):
        try:
            os.remove(f)
        except Exception:
            pass

def main():
    if os.path.exists('.env'):
        with open('.env', 'r', encoding='utf-8-sig') as f:
            for line in f:
                if line.strip() and not line.startswith('#') and '=' in line:
                    k, v = line.strip().split('=', 1)
                    os.environ[k.strip()] = v.strip()

    parser = argparse.ArgumentParser(
        description="Local Lead Generator 2.0 - Modular Pipeline & Plugin Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --recipe recipes/web_design.yaml
  python main.py --url https://tallylawncare.com
  python main.py --recipe recipes/b2b_saas.yaml --limit 5
  python main.py --reset-low-scores
        """
    )
    parser.add_argument("--recipe", type=str, default="recipes/web_design.yaml", help="Path to YAML recipe file")
    parser.add_argument("--url", type=str, help="Run audit on a single URL")
    parser.add_argument("--name", type=str, help="Business name for single URL audit")
    parser.add_argument("--phone", type=str, help="Phone number for single URL audit")
    parser.add_argument("--location", type=str, help="Location for single URL audit")
    parser.add_argument("--limit", type=int, help="Override maximum leads to harvest per search")
    parser.add_argument("--queries", type=str, help="Comma separated list of queries to override recipe")
    parser.add_argument("--locations", type=str, help="Comma separated list of locations to override recipe")
    parser.add_argument("--config", action='append', help="Override config values (e.g. --config job_type=FULLTIME)")
    parser.add_argument("--reset-low-scores", action="store_true", help="Clear low score entries from local cache")
    args = parser.parse_args()

    clean_locks()

    if args.reset_low_scores:
        clear_low_scores("seen_leads.json")
        return

    try:
        recipe = load_recipe(args.recipe)
    except Exception as e:
        log(f"Error loading recipe '{args.recipe}': {e}")
        return

    if args.limit:
        if "config" not in recipe:
            recipe["config"] = {}
        recipe["config"]["max_leads"] = args.limit

    if args.queries:
        recipe["queries"] = [q.strip() for q in args.queries.split(",")]
        
    if args.locations:
        recipe["locations"] = [l.strip() for l in args.locations.split(",")]
        
    if args.config:
        if "config" not in recipe:
            recipe["config"] = {}
        for c in args.config:
            k, v = c.split("=", 1)
            recipe["config"][k] = v

    engine = PipelineEngine(recipe)

    print("=" * 60)
    print(f" Local Lead Generator 2.0: {recipe.get('name', 'Pipeline Engine')}")
    print(f" Pipeline Modules: {', '.join(recipe.get('pipeline', []))}")
    print("=" * 60)

    if args.url:
        result = engine.run_url(
            args.url,
            business_name=args.name or "Manual Target",
            phone=args.phone or "",
            location=args.location or ""
        )
        print("\n" + "=" * 60)
        print(f" Audit Result for: {result.business_name} ({result.website_url})")
        print(f" Score: {result.html_score} points | Gemini Score: {result.gemini_score}")
        print(f" Flaws: {result.audit_bullet_points}")
        print(f" Owner: {result.owner_name} ({result.owner_source})")
        print(f" Recommended Pitch: {result.recommended_tools}")
        print("=" * 60)
        
        prefix = recipe.get("config", {}).get("html_prefix", "leads_")
        out_file = os.path.abspath(os.path.join("output", f"{prefix}{datetime.now().strftime('%Y%m%d')}.html"))
        if os.path.exists(out_file):
            webbrowser.open(f"file://{out_file}")
        return

    engine.run()

    prefix = recipe.get("config", {}).get("html_prefix", "leads_")
    out_file = os.path.abspath(os.path.join("output", f"{prefix}{datetime.now().strftime('%Y%m%d')}.html"))
    if os.path.exists(out_file):
        log(f"Pipeline complete! Opening HTML report: {out_file}")
        webbrowser.open(f"file://{out_file}")
    else:
        log("Pipeline execution complete.")

if __name__ == "__main__":
    main()
