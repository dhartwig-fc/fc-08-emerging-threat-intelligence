#!/bin/bash
# The fourteen advisories with no predicted record, shortest first.
#
# WHY A SCRIPT AND NOT AN AGENT. Everything shares one quota meter: the
# extractions go through the same `claude` CLI on the same subscription as any
# agent would. An agent supervising this loop spends its own reasoning tokens
# competing with the work it supervises. Three agents launched 2026-09-12 died
# on the session limit in minutes having produced nothing.
#
# RESUMABLE AND IDEMPOTENT: skips any advisory whose record already exists, so a
# session limit costs at most the run in flight. Relaunch and it continues.
# Shortest documents first so a limited window banks the most records.
set -u
cd /Users/danhartwig/fc-08-emerging-threat-intelligence || exit 2
. .venv/bin/activate
unset ANTHROPIC_API_KEY   # takes precedence over the subscription token if left set

LOG=data/repeats/batch14.log
mkdir -p data/repeats
run () {
  id="$1"; pdf="$2"; pages="$3"
  if [ -s "data/records/$id.json" ]; then echo "  $id already done"; return 0; fi
  echo "=== $id (${pages}p) $(date +%H:%M)"
  python agents/extract_advisory.py "data/advisories/$pdf" --advisory-id "$id" 2>&1 | tail -3 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  if [ "$rc" -ne 0 ]; then echo "  FAILED rc=$rc (recorded, continuing)" | tee -a "$LOG"; fi
}

run ADV-2026-0011 fincen-chinese-ml-networks-2025.pdf 15
run ADV-2026-0015 necc-red-alert-russian-elites-2022.pdf 15
run ADV-2026-0010 fincen-iran-oil-smuggling-2025.pdf 18
run ADV-2026-0005 fatf-virtual-assets-red-flags-2020.pdf 24
run ADV-2026-0014 ofsi-financial-services-threat-2025.pdf 29
run ADV-2026-0018 fca-tr19-4-capital-markets-ml-2019.pdf 30
run ADV-2026-0012 ofac-maritime-advisory-2020.pdf 35
run ADV-2026-0003 fatf-professional-money-laundering-2018.pdf 53
run ADV-2026-0006 fatf-environmental-crime-2021.pdf 70
run ADV-2026-0007 fatf-cyber-enabled-fraud-2023.pdf 72
run ADV-2026-0008 fatf-pml-underground-banking-hawala-2026.pdf 76
run ADV-2026-0020 wolfsberg-trade-finance-principles-2019.pdf 83
run ADV-2026-0019 europol-eu-socta-2025.pdf 100
run ADV-2026-0004 fatf-egmont-concealment-beneficial-ownership-2018.pdf 190

echo "--- records now: $(ls -1 data/records/ADV-*.json | grep -vc 'schema-\|week1') of 20 ---"
