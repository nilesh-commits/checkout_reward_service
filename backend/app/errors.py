"""Structured, distinguishable API errors.

Every failure an API client can hit is a `DomainError` carrying a stable machine
`code`, a human `message`, an HTTP `status`, and optional `details`. The exception
handler in `main.py` renders them all as:

    { "error": { "code", "message", "details" } }

Stable codes let clients branch on failure mode without string-matching messages.
"""
from typing import Any


class DomainError(Exception):
    code: str = "INTERNAL_ERROR"
    status: int = 500
    message: str = "Internal error"

    def __init__(self, message: str | None = None, details: Any = None):
        self.message = message or self.message
        self.details = details
        super().__init__(self.message)


# --- 404 ---
class CartNotFound(DomainError):
    code, status, message = "CART_NOT_FOUND", 404, "Cart not found"


class ProductNotFound(DomainError):
    code, status, message = "PRODUCT_NOT_FOUND", 404, "Product not found"


class OrderNotFound(DomainError):
    code, status, message = "ORDER_NOT_FOUND", 404, "Order not found"


class CartItemNotFound(DomainError):
    code, status, message = "CART_ITEM_NOT_FOUND", 404, "Item not in cart"


# --- 400 / 422 (validation) ---
class ValidationError(DomainError):
    code, status, message = "VALIDATION_ERROR", 422, "Invalid request"


class CartEmpty(DomainError):
    code, status, message = "CART_EMPTY", 400, "Cannot checkout an empty cart"


# --- 409 (conflict / business-rule) ---
class InsufficientInventory(DomainError):
    code, status, message = (
        "INSUFFICIENT_INVENTORY",
        409,
        "Not enough inventory to fulfil the order",
    )


class CouponInvalidOrRedeemed(DomainError):
    code, status, message = (
        "COUPON_INVALID_OR_REDEEMED",
        409,
        "Coupon does not exist or has already been redeemed",
    )


class MilestoneNotReached(DomainError):
    code, status, message = (
        "MILESTONE_NOT_REACHED",
        409,
        "No eligible unrewarded order milestone yet",
    )


class CouponAlreadyGenerated(DomainError):
    code, status, message = (
        "COUPON_ALREADY_GENERATED",
        409,
        "A coupon has already been generated for the current milestone",
    )


# --- 401 ---
class Unauthorized(DomainError):
    code, status, message = "UNAUTHORIZED", 401, "Admin token required"
