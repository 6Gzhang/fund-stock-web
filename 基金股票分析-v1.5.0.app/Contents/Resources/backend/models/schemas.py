from pydantic import BaseModel
from typing import Optional


class QuoteResponse(BaseModel):
    code: str
    name: str
    price: float
    change: float
    change_pct: float
    open: float
    high: float
    low: float
    volume: float
    amount: float
    type: str  # "stock" or "fund"


class TradeRequest(BaseModel):
    code: str
    name: str
    type: str
    action: str  # "buy" or "sell"
    shares: float
    price: float


class PositionResponse(BaseModel):
    code: str
    name: str
    type: str
    shares: float
    avg_cost: float
    current_price: Optional[float] = None
    market_value: Optional[float] = None
    profit: Optional[float] = None
    profit_pct: Optional[float] = None


class WatchlistItem(BaseModel):
    code: str
    name: str
    type: str


class AnalysisRequest(BaseModel):
    code: str
    name: str
    type: str


class AnalysisResponse(BaseModel):
    code: str
    name: str
    recommendation: str  # "buy" / "sell" / "hold"
    confidence: float
    reasoning: str
    suggested_ratio: float  # 建议仓位占比