#!/usr/bin/env python3
"""Filter EPA's ECHO Exporter down to the slim subset the Hub serves.

Keeps active facilities with any enforcement signal (qtrs in noncompliance,
formal/informal actions, penalties, SNC or HPV flags). Used by the weekly
GitHub Action; same logic produced the initial data/echo_slim.csv.gz.

Usage: unzip -p echo_exporter.zip ECHO_EXPORTER.csv | python3 filter_echo.py /dev/stdin out.csv
"""
import sys, csv

inp, outp = sys.argv[1], sys.argv[2]
r = csv.reader(open(inp, newline="", encoding="utf-8", errors="replace"))
w = csv.writer(open(outp, "w", newline=""))
hdr = next(r)
ix = {n: i for i, n in enumerate(hdr)}
cols = ["REGISTRY_ID", "FAC_NAME", "FAC_CITY", "FAC_STATE", "FAC_MAJOR_FLAG",
        "FAC_INSPECTION_COUNT", "FAC_DATE_LAST_INSPECTION", "FAC_INFORMAL_COUNT",
        "FAC_FORMAL_ACTION_COUNT", "FAC_TOTAL_PENALTIES", "FAC_QTRS_WITH_NC",
        "FAC_COMPLIANCE_STATUS", "FAC_SNC_FLG", "CAA_HPV_FLAG", "FAC_NAICS_CODES"]
idx = [ix[c] for c in cols]
ACT, Q, F = ix["FAC_ACTIVE_FLAG"], ix["FAC_QTRS_WITH_NC"], ix["FAC_FORMAL_ACTION_COUNT"]
P, S, H, INF = ix["FAC_TOTAL_PENALTIES"], ix["FAC_SNC_FLG"], ix["CAA_HPV_FLAG"], ix["FAC_INFORMAL_COUNT"]
w.writerow(["registry_id", "name", "city", "state", "major", "insp_count", "last_insp",
            "informal_count", "formal_count", "penalties", "qtrs_nc", "status", "snc", "hpv", "naics"])
tot = kept = 0
for row in r:
    tot += 1
    try:
        if row[ACT] != "Y":
            continue
        if (row[Q] not in ("", "0")) or (row[F] not in ("", "0")) or \
           (row[P] not in ("", "0", "0.0")) or row[S] == "Y" or row[H] == "Y" or \
           (row[INF] not in ("", "0")):
            kept += 1
            w.writerow([row[i] for i in idx])
    except IndexError:
        continue
print(f"total {tot} kept {kept}", file=sys.stderr)
