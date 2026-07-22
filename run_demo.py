"""Demo entrypoint: python run_demo.py [--no-ai]"""
import sys, os
from recon.pipeline import run, summarise

if __name__ == "__main__":
    use_ai = "--no-ai" not in sys.argv
    if use_ai and not os.environ.get("ANTHROPIC_API_KEY"):
        print("[i] No ANTHROPIC_API_KEY — running deterministic engine only.\n")
        use_ai = False
    print(summarise(run(use_ai=use_ai)))
