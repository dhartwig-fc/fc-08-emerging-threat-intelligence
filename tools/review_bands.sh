#!/bin/bash
# Three repeats of the additive reviewer across the four documents where the
# 2026-09-13 shape count found misses concentrate in indicator sections:
#   ADV-2026-0016 7 of 7 | ADV-2026-0015 7 of 8 | ADV-2026-0009 5 of 6 | ADV-2026-0004 12 of 17
#
# One run at a time -- everything shares one quota meter, and three concurrent
# agents produced nothing on 2026-09-12. Resumable: skips outputs that exist, so
# a session limit costs at most the run in flight. Shortest documents first.
set -u
cd /Users/danhartwig/fc-08-emerging-threat-intelligence || exit 2
. .venv/bin/activate
unset ANTHROPIC_API_KEY

run () {
  rep="$1"; id="$2"; pdf="$3"
  out="data/reviewed/rep$rep/$id.additions.json"
  if [ -s "$out" ]; then echo "  rep$rep $id already done"; return 0; fi
  mkdir -p "data/reviewed/rep$rep"
  echo "=== rep$rep $id $(date +%H:%M)"
  python agents/review_advisory.py "data/advisories/$pdf" --record "data/records/$id.json" --out "$out" 2>&1 | tail -2
}

for rep in 1 2 3; do
  run $rep ADV-2026-0016 necc-red-alert-high-risk-goods.pdf
  run $rep ADV-2026-0009 fincen-kleptocracy-2022.pdf
  run $rep ADV-2026-0015 necc-red-alert-russian-elites-2022.pdf
  run $rep ADV-2026-0004 fatf-egmont-concealment-beneficial-ownership-2018.pdf
done
echo "--- additions files: $(find data/reviewed -name '*.additions.json' | wc -l | tr -d ' ') of 12 ---"
