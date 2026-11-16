from enum import StrEnum


class Currency(StrEnum):
    USD = "USD"
    ARS = "ARS"
    USDC = "USDC"
    USDT = "USDT"


class TaxRegime(StrEnum):
    MONOTRIBUTO = "monotributo"


class ActivityType(StrEnum):
    SERVICES = "services"
    GOODS = "goods"


class MonotributoCategory(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"
    G = "G"
    H = "H"
    I = "I"  # noqa: E741
    J = "J"
    K = "K"


class MovementType(StrEnum):
    INCOMING_TRANSFER = "incoming_transfer"
    OUTGOING_TRANSFER = "outgoing_transfer"
    INTERNAL_TRANSFER = "internal_transfer"
    CARD_PAYMENT = "card_payment"
    CONVERSION = "conversion"
    YIELD_CREDIT = "yield_credit"
    REFUND = "refund"


class Direction(StrEnum):
    IN = "in"
    OUT = "out"
