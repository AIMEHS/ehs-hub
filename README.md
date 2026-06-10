# EHS Hub

Source for the EHS Compliance Hub at https://hub.aim-env.com — auto-deployed via Vercel.

## Data

- `data/echo_slim.csv.gz` — slim subset of EPA's ECHO Exporter (facilities with enforcement
  signal). Refreshed weekly by the `echo-refresh` GitHub Action.
- `data/adi.json.gz` — EPA Applicability Determination Index (all determinations: metadata,
  EPA abstracts, subpart tags). Public-domain EPA data scraped politely from
  https://cfpub.epa.gov/adi/ by `scripts/scrape_adi.py`; `scripts/build_adi_sql.py` turns a
  scrape into Supabase upserts + this artifact. EPA last added determinations in 2020, so a
  manual re-scrape a few times a year is plenty.
