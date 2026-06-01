from typing import Literal

from pydantic import BaseModel, Field


class ClassifiedSegment(BaseModel):
    label: Literal["DK", "PK", "CK", "DOM", "NONE"]
    exact_quote: str = Field(
        description="The exact word-for-word quote from the transcript that corresponds to this label."
    )
    confidence_score: float = Field(
        description="Confidence score for this specific classification between 0.0 and 1.0."
    )


class ChatClassification(BaseModel):
    annotations: list[ClassifiedSegment] = Field(
        description="A list of classified segments (quotes with their labels) found in the transcript."
    )

