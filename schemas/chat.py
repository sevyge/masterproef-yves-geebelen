from typing import Literal

from pydantic import BaseModel


class ChatClassification(BaseModel):
    labels: list[Literal["DK", "PK", "CK", "DOM", "NONE"]]
    confidence_score: float
