from dataclasses import dataclass
from datetime import datetime
from typing import Any


status = {
    'usedup': 'исчерпан дневной лимит',
    'running': 'запущена'
}

def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

@dataclass(slots=True)
class Item:
    sku: int
    name: str
    bid: float
    quantity: int
    category: str
    category_id: int
    keywords: list[str]

@dataclass(slots=True)
class Campaign:
    campaign_id: int
    name: str
    campaign_type: str
    payment_model: str
    budget_total: int
    from_date: datetime
    regions: list[int]
    status: str
    spent_daily: int
    spent_total: int
    shows: int
    clicks: int
    created_at: datetime
    updated_at: datetime
    items: list[Item]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Campaign":
        return cls(
            campaign_id=data["campaign_id"],
            name=data["name"],
            campaign_type=data["campaign_type"],
            payment_model=data["payment_model"],
            budget_total=data["budget_total"],
            from_date=parse_dt(data["from_date"]),
            regions=data["regions"],
            status=status.get(data["status"], data["status"]),
            spent_daily=data["spent_daily"],
            spent_total=data["spent_total"],
            shows=data["shows"],
            clicks=data["clicks"],
            created_at=parse_dt(data["created_at"]),
            updated_at=parse_dt(data["updated_at"]),
            items=[]
        )
