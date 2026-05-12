from dataclasses import dataclass
from enum import Enum


class OrderStatus(Enum):
    PENDING = "P"
    NEW = "0"
    PARTIALLY_FILLED = "1"
    FILLED = "2"
    CANCELED = "4"
    REPLACED = "5"
    REJECTED = "8"


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
    # Validates FIX order status transitions
    TRANSITIONS = {
        OrderStatus.PENDING.value: [OrderStatus.NEW.value, OrderStatus.REJECTED.value],
        OrderStatus.NEW.value: [OrderStatus.PARTIALLY_FILLED.value, OrderStatus.FILLED.value, OrderStatus.CANCELED.value, OrderStatus.REPLACED.value],
        OrderStatus.PARTIALLY_FILLED.value: [OrderStatus.PARTIALLY_FILLED.value, OrderStatus.FILLED.value, OrderStatus.CANCELED.value, OrderStatus.REPLACED.value],
        OrderStatus.FILLED.value: [],
        OrderStatus.CANCELED.value: [],
        OrderStatus.REPLACED.value: [OrderStatus.PARTIALLY_FILLED.value, OrderStatus.FILLED.value, OrderStatus.CANCELED.value, OrderStatus.REPLACED.value],
        OrderStatus.REJECTED.value: [],
    }

    @classmethod
    def can_transition(cls, current_state: str, next_state: str) -> bool:
        if current_state not in cls.TRANSITIONS:
            return False
        return next_state in cls.TRANSITIONS[current_state]

    @classmethod
    def is_terminal(cls, state: str) -> bool:
        return state in (OrderStatus.FILLED.value, OrderStatus.CANCELED.value, OrderStatus.REJECTED.value)
