"""
NEXUS Track 2 · Threat Intelligence · Slice 1
Week 1 contract: the structured record every advisory must be reduced to.

This schema is the treaty between the extraction agent and the Knowledge Centre.
Everything downstream (MCP tools, evals, telemetry, digest routing) validates
against it. Change it deliberately and version it.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.3.0"
# 1.3.0 (2026-09-11, week 3 golden set): extraction_notes cap 1000 -> 4000. Six golden
#   labels on 50-190 page reports failed validation on reviewer notes alone; truncating
#   them would discard the judgement calls the owner review exists to read.
# 1.2.0 (2026-09-10, week 2, on importing the governed FC10 library):
#   - typology_id pattern allows one trailing letter: the governed library carries
#     TBML002U (under-invoicing, re-slotted beside fc-10's load-bearing TBML002)
# 1.1.0 (2026-09-10, after the first real extraction, see evals/review_ADV-2026-0001.md):
#   - Citation.page is the PDF page index, not the printed folio; printed_folio added
#   - AdvisorySource.published_on_precision added; a day the source never states is not a fact
#   - ActorType.CATEGORY added for threat-actor classes such as "professional money launderers"


class SourceType(str, Enum):
    FATF = "fatf"
    OFAC = "ofac"
    OFSI = "ofsi"
    NCA = "nca"
    FCA = "fca"
    FINCEN = "fincen"
    EUROPOL = "europol"
    WOLFSBERG = "wolfsberg"
    INDUSTRY = "industry"
    PRESS = "press"
    OTHER = "other"


class TypologyFamily(str, Enum):
    """Mirror of the Knowledge Centre families. Keep in step with data/typologies.json."""
    TBML = "tbml"
    SANCTIONS = "sanctions"
    CORRESPONDENT = "correspondent_banking"
    CAPITAL_MARKETS = "capital_markets"
    NETWORK = "network"
    FRAUD = "fraud"
    CRYPTO = "crypto"
    CORRUPTION = "corruption"
    TERRORIST_FINANCING = "terrorist_financing"
    OTHER = "other"


class ActorType(str, Enum):
    PERSON = "person"
    ORGANISATION = "organisation"
    VESSEL = "vessel"
    WALLET = "wallet"
    JURISDICTION = "jurisdiction"
    NETWORK = "network"
    CATEGORY = "category"  # a class of actor the source describes, not a named party
    UNKNOWN = "unknown"


class DatePrecision(str, Enum):
    """How much of published_on the source actually states."""
    DAY = "day"
    MONTH = "month"
    YEAR = "year"


class IndicatorType(str, Enum):
    BEHAVIOURAL = "behavioural"
    TRANSACTIONAL = "transactional"
    DOCUMENTARY = "documentary"
    NETWORK = "network"
    GEOGRAPHIC = "geographic"
    PRODUCT = "product"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Desk(str, Enum):
    """Digest routing targets. Week 5 wires these to the routing rule."""
    TRADE = "trade_desk"
    SANCTIONS = "sanctions_desk"
    CORRESPONDENT = "correspondent_desk"
    MARKETS = "markets_desk"
    FRAUD = "fraud_desk"
    FIU = "fiu_liaison"
    GENERAL = "general_intel"


class Citation(BaseModel):
    """Every extracted fact points back to the exact place it came from."""
    model_config = ConfigDict(extra="forbid")

    page: int = Field(
        ...,
        ge=1,
        description=(
            "1-based PDF page index, the n in the '=== PAGE n ===' marker the text was shown under. "
            "NOT the page number printed on the page; that goes in printed_folio."
        ),
    )
    printed_folio: Optional[str] = Field(
        None, max_length=12, description="The page number as printed on the page, if any, for human readers"
    )
    paragraph: Optional[int] = Field(None, ge=1, description="1-based paragraph on that page")
    quote: str = Field(..., min_length=10, max_length=600, description="Verbatim supporting text")


class TypologyReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family: TypologyFamily
    typology_id: Optional[str] = Field(
        None,
        pattern=r"^[A-Z]{2,6}\d{3}[A-Z]?$",
        description="Knowledge Centre ID such as TBML001 or TBML002U. None means emergent candidate.",
    )
    label: str = Field(..., min_length=3, max_length=120)
    emergent: bool = Field(False, description="True when no existing typology matches")
    confidence: Confidence
    citations: List[Citation] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _emergent_has_no_id(self) -> "TypologyReference":
        if self.emergent and self.typology_id is not None:
            raise ValueError("An emergent typology cannot carry an existing typology_id")
        if not self.emergent and self.typology_id is None:
            raise ValueError("A non-emergent typology must carry a typology_id")
        return self


class Actor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=2, max_length=200)
    actor_type: ActorType
    aliases: List[str] = Field(default_factory=list, max_length=20)
    jurisdiction: Optional[str] = Field(None, pattern=r"^[A-Z]{2}$", description="ISO 3166-1 alpha-2")
    role: Optional[str] = Field(None, max_length=200, description="Role in the scheme as stated")
    confidence: Confidence
    citations: List[Citation] = Field(..., min_length=1)

    @field_validator("aliases")
    @classmethod
    def _dedupe_aliases(cls, v: List[str]) -> List[str]:
        seen = []
        for a in v:
            a = a.strip()
            if a and a.lower() not in [s.lower() for s in seen]:
                seen.append(a)
        return seen


class Indicator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    indicator_type: IndicatorType
    description: str = Field(..., min_length=10, max_length=500)
    detectable_in_transaction_data: bool = Field(
        ..., description="Can a monitoring rule see this, or is it only visible to a human"
    )
    confidence: Confidence
    citations: List[Citation] = Field(..., min_length=1)


class AdvisorySource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: SourceType
    publisher: str = Field(..., min_length=2, max_length=120)
    title: str = Field(..., min_length=3, max_length=300)
    published_on: date
    published_on_precision: DatePrecision = Field(
        DatePrecision.DAY,
        description="day if the source states a full date; month or year if it does not. Unstated parts are 1.",
    )
    url: Optional[str] = Field(None, max_length=500)
    document_sha256: str = Field(..., pattern=r"^[a-f0-9]{64}$", description="Hash of the ingested file")
    page_count: int = Field(..., ge=1)

    @model_validator(mode="after")
    def _unstated_date_parts_are_one(self) -> "AdvisorySource":
        if self.published_on_precision == DatePrecision.MONTH and self.published_on.day != 1:
            raise ValueError("month precision requires day == 1")
        if self.published_on_precision == DatePrecision.YEAR and (self.published_on.month, self.published_on.day) != (1, 1):
            raise ValueError("year precision requires month == 1 and day == 1")
        return self


class AdvisoryRecord(BaseModel):
    """
    The unit of intel extraction. One advisory in, one validated record out.
    Nothing reaches the Knowledge Centre unless it passes this model.
    """
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(SCHEMA_VERSION, pattern=r"^\d+\.\d+\.\d+$")
    advisory_id: str = Field(
        ...,
        pattern=r"^ADV-\d{4}-\d{4}$",
        description="Governed ID assigned at ingestion, for example ADV-2026-0001",
    )
    source: AdvisorySource
    summary: str = Field(..., min_length=50, max_length=1500, description="Plain-English summary, no new claims")
    jurisdictions: List[str] = Field(default_factory=list, description="ISO 3166-1 alpha-2 codes")
    typologies: List[TypologyReference] = Field(..., min_length=1)
    actors: List[Actor] = Field(default_factory=list)
    indicators: List[Indicator] = Field(default_factory=list)
    suggested_desks: List[Desk] = Field(..., min_length=1)
    overall_confidence: Confidence
    extraction_notes: Optional[str] = Field(None, max_length=4000, description="Agent caveats for the human reviewer")

    @field_validator("jurisdictions")
    @classmethod
    def _iso_codes(cls, v: List[str]) -> List[str]:
        out = []
        for code in v:
            code = code.strip().upper()
            if len(code) != 2 or not code.isalpha():
                raise ValueError("jurisdictions must be ISO 3166-1 alpha-2 codes, got %r" % code)
            if code not in out:
                out.append(code)
        return out

    @property
    def emergent_candidates(self) -> List[TypologyReference]:
        return [t for t in self.typologies if t.emergent]


if __name__ == "__main__":
    import json
    print(json.dumps(AdvisoryRecord.model_json_schema(), indent=2))
