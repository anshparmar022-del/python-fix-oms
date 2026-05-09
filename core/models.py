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


class OrderStateMachine:
    # Validates FIX order status transitions (0=New, 1=Partial, 2=Filled, 4=Cancelled, 5=Replaced, 8=Rejected)
    TRANSITIONS = {
        "0": ["1", "2", "4", "5"],
        "1": ["1", "2", "4"],
        "2": [],
        "4": [],
        "5": ["1", "2", "4", "5"],
        "8": [],
    }

    @classmethod
    def can_transition(cls, current_state: str, next_state: str) -> bool:
        if current_state not in cls.TRANSITIONS:
            return False
        return next_state in cls.TRANSITIONS[current_state]

    @classmethod
    def is_terminal(cls, state: str) -> bool:
        return state in ("2", "4", "8")
