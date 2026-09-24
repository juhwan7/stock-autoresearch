# AGENTS.md

## Mission
Build and maintain an autonomous stock research system. The system discovers what is worth researching before it writes a report.

## Non-negotiable rules
1. Keep this repository independent. Do not import files, state, prompts, or assumptions from market-memo.
2. Prefer primary sources: regulators, exchanges, filings, government documents, company IR/newsrooms, central banks, court/legal records.
3. A news article alone does not upgrade a claim to confirmed fact.
4. Separate: verified fact / company or official claim / third-party analysis / inference / unverified item.
5. Dates, money, percentages, production capacity, ownership, contracts, and market statistics should be tied to the strongest available source.
6. Search for disconfirming evidence. A research result without a serious counter-case is incomplete.
7. Do not turn thematic association into company exposure. Stock mapping requires a concrete business link.
8. Do not issue buy/sell recommendations. This project produces research evidence, not personalized investment advice.
9. Preserve machine-readable run artifacts under data/runs and human-readable reports under reports.
10. Avoid silent failures. If live research cannot verify a material point, keep it explicitly unknown.

## Development
- Python 3.11+
- Run tests: `pytest`
- End-to-end without API key: `python -m autoresearch run --mode dry-run`
- Live: set `OPENAI_API_KEY`, then `python -m autoresearch run --mode live`

## Architecture
Scanner -> scoring -> topic selection -> Researcher -> Critic -> optional re-research -> Chief Researcher -> report/state.
