#!/bin/bash
# The additive reviewer over the sixteen documents NOT in the acceptance bands.
# One repeat each: the bands already established repeatability on the four where
# misses concentrate. This measures REACH -- eight of these have zero misses in
# indicator sections, so the expected lift here is small and may be zero.
# Resumable, one at a time, shortest first.
set -u
cd /Users/danhartwig/fc-08-emerging-threat-intelligence || exit 2
. .venv/bin/activate
unset ANTHROPIC_API_KEY
mkdir -p data/reviewed/rest

run () {
  id="$1"; pdf="$2"; pages="$3"
  out="data/reviewed/rest/$id.additions.json"
  if [ -s "$out" ]; then echo "  $id already done"; return 0; fi
  echo "=== $id (${pages}p) $(date +%H:%M)"
  python agents/review_advisory.py "data/advisories/$pdf" --record "data/records/$id.json" --out "$out" 2>&1 | tail -2
}

run ADV-2026-0013 ofac-triseal-intermediaries-2023.pdf 6
run ADV-2026-0017 necc-red-alert-shadow-fleet.pdf 8
run ADV-2026-0002 fatf-tbml-risk-indicators-2021.pdf 10
run ADV-2026-0011 fincen-chinese-ml-networks-2025.pdf 15
run ADV-2026-0010 fincen-iran-oil-smuggling-2025.pdf 18
run ADV-2026-0005 fatf-virtual-assets-red-flags-2020.pdf 24
run ADV-2026-0014 ofsi-financial-services-threat-2025.pdf 29
run ADV-2026-0018 fca-tr19-4-capital-markets-ml-2019.pdf 30
run ADV-2026-0012 ofac-maritime-advisory-2020.pdf 35
run ADV-2026-0003 fatf-professional-money-laundering-2018.pdf 53
run ADV-2026-0001 fatf-tbml-2020.pdf 66
run ADV-2026-0006 fatf-environmental-crime-2021.pdf 70
run ADV-2026-0007 fatf-cyber-enabled-fraud-2023.pdf 72
run ADV-2026-0008 fatf-pml-underground-banking-hawala-2026.pdf 76
run ADV-2026-0020 wolfsberg-trade-finance-principles-2019.pdf 83
run ADV-2026-0019 europol-eu-socta-2025.pdf 100

echo "--- rest: $(ls -1 data/reviewed/rest | wc -l | tr -d ' ') of 16 ---"
