from dataclasses import dataclass
from enum import Enum

class OrderStatus(Enum):
    PENDING = "PENDING"
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REPLACED = "REPLACED"
    REJECTED = "REJECTED"

@dataclass
class Order:
    id: str
    symbol: str
    side: str
    qty: float
    price: float
    client_id: str
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: float = 0.0
    avg_price: float = 0.0
    leaves_qty: float = 0.0
