from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class OrderSide(str, Enum):
    BUY  = "1"
    SELL = "2"


class OrderStatus(str, Enum):
    PENDING          = "PENDING"
    NEW              = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED           = "FILLED"
    CANCELED         = "CANCELED"
    REPLACED         = "REPLACED"
    REJECTED         = "REJECTED"


@dataclass
class Order:
    id:         str
    symbol:     str
    side:       OrderSide
    qty:        float
    price:      float
    status:     OrderStatus = OrderStatus.PENDING
    filled_qty: float       = 0.0
    avg_price:  float       = 0.0
    timestamp:  str         = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "symbol":     self.symbol,
            "side":       self.side,
            "qty":        self.qty,
            "price":      self.price,
            "status":     self.status,
            "filled_qty": self.filled_qty,
            "avg_price":  self.avg_price,
            "timestamp":  self.timestamp,
        }

    @property
    def leaves_qty(self) -> float:
        """Remaining unfilled quantity."""
        return self.qty - self.filled_qty

    @property
    def is_active(self) -> bool:
        return self.status in (OrderStatus.PENDING, OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED)
