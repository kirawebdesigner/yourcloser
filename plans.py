"""
YourCloser plan definitions and feature gates.
Keep this module pure so handlers, DB helpers, and tests share one source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    code: str
    name: str
    monthly_etb: int | None
    setup_fee_etb: int | None
    max_products: int | None
    max_admins: int | None
    can_broadcast: bool
    can_advanced_catalog: bool
    can_advanced_reporting: bool
    support_level: str


PLANS: dict[str, Plan] = {
    "starter": Plan(
        code="starter",
        name="Starter",
        monthly_etb=999,
        setup_fee_etb=0,
        max_products=30,
        max_admins=1,
        can_broadcast=False,
        can_advanced_catalog=False,
        can_advanced_reporting=False,
        support_level="basic",
    ),
    "growth": Plan(
        code="growth",
        name="Growth",
        monthly_etb=2499,
        setup_fee_etb=3000,
        max_products=150,
        max_admins=1,
        can_broadcast=True,
        can_advanced_catalog=True,
        can_advanced_reporting=False,
        support_level="priority",
    ),
    "pro": Plan(
        code="pro",
        name="Pro",
        monthly_etb=4999,
        setup_fee_etb=7500,
        max_products=500,
        max_admins=5,
        can_broadcast=True,
        can_advanced_catalog=True,
        can_advanced_reporting=True,
        support_level="faster",
    ),
    "custom": Plan(
        code="custom",
        name="Custom",
        monthly_etb=None,
        setup_fee_etb=None,
        max_products=None,
        max_admins=None,
        can_broadcast=True,
        can_advanced_catalog=True,
        can_advanced_reporting=True,
        support_level="dedicated",
    ),
}


DEFAULT_PLAN_CODE = "starter"
ACTIVE_STATUSES = {"active", "trialing"}


def normalize_plan_code(plan_code: str | None) -> str:
    code = (plan_code or DEFAULT_PLAN_CODE).strip().lower()
    return code if code in PLANS else DEFAULT_PLAN_CODE


def get_plan(plan_code: str | None) -> Plan:
    return PLANS[normalize_plan_code(plan_code)]


def build_plan_record(shop: dict | None) -> dict:
    shop = shop or {}
    plan = get_plan(shop.get("plan"))
    custom_limits = shop.get("custom_limits") if isinstance(shop.get("custom_limits"), dict) else {}

    def custom_or_default(key: str, default):
        value = custom_limits.get(key)
        return default if value is None else value

    return {
        "code": plan.code,
        "name": plan.name,
        "monthly_etb": plan.monthly_etb,
        "setup_fee_etb": plan.setup_fee_etb,
        "status": shop.get("plan_status") or "active",
        "max_products": custom_or_default("max_products", plan.max_products),
        "max_admins": custom_or_default("max_admins", plan.max_admins),
        "can_broadcast": bool(custom_or_default("can_broadcast", plan.can_broadcast)),
        "can_advanced_catalog": bool(custom_or_default("can_advanced_catalog", plan.can_advanced_catalog)),
        "can_advanced_reporting": bool(custom_or_default("can_advanced_reporting", plan.can_advanced_reporting)),
        "support_level": custom_or_default("support_level", plan.support_level),
    }


def is_plan_active(plan_record: dict) -> bool:
    return str(plan_record.get("status", "")).lower() in ACTIVE_STATUSES


def describe_limit(value: int | None) -> str:
    return "Unlimited" if value is None else str(value)
