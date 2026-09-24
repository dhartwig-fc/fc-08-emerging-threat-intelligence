"""
Who a run is -- told to the MCP server by the runner, never by the agent.

propose_link used to record whatever advisory_id the agent passed and nothing
else about where a proposal came from. Measured 2026-09-24: 383 proposals, none
naming its run, so a reviewer could not trace one to a record or a document.
The runner now builds one of these per run and hands the server its env(); the
agent cannot set or change any of it.
"""

from __future__ import annotations

import secrets
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.citation_match import file_sha256  # noqa: E402
# The gate quarantines a stage not in this tuple, so the runner reads the same one.
from schemas.proposal_contract import STAGES  # noqa: E402

QUEUE_DIR = ROOT / "data" / "proposals"


@dataclass(frozen=True)
class RunIdentity:
    run_id: str
    stage: str
    advisory_id: str
    pdf_path: Path
    pdf_sha256: str

    def __post_init__(self) -> None:
        if self.stage not in STAGES:
            raise ValueError("stage must be one of %s, got %r" % (STAGES, self.stage))

    @classmethod
    def new(cls, stage: str, advisory_id: str, pdf_path: Path) -> "RunIdentity":
        pdf_path = Path(pdf_path).resolve()
        run_id = "%s-%s-%s" % (advisory_id.lower(), stage, secrets.token_hex(5))
        return cls(run_id, stage, advisory_id, pdf_path, file_sha256(pdf_path))

    @property
    def queue_path(self) -> Path:
        # One tracked file per run: never appended to by two processes, and in
        # every clone. See the spec's amended Section 1.
        return QUEUE_DIR / ("%s.jsonl" % self.run_id)

    def env(self) -> dict:
        return {
            "NEXUS_RUN_ID": self.run_id,
            "NEXUS_STAGE": self.stage,
            "NEXUS_ADVISORY_ID": self.advisory_id,
            "NEXUS_PDF_PATH": str(self.pdf_path),
            "NEXUS_PDF_SHA256": self.pdf_sha256,
            "NEXUS_PROPOSALS_PATH": str(self.queue_path),
        }
