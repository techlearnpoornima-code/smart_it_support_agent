"""Dangerous-action detection, authorization checks, and multi-intent priority."""

from models.intent import SessionState

SOFTWARE_COST_LIMIT_IN_DOLLARS = 100

# Priority order for multi-intent resolution (highest → lowest)
INTENT_PRIORITY: list[str] = [
    "reset_password",    # security
    "hardware_issue",    # hardware
    "software_request",  # software
    "check_leave",       # leave
    "policy_lookup",     # policy
]

# Each lambda returns True if the action requires HITL confirmation
DANGEROUS_ACTIONS: dict[str, object] = {
    "reset_password":    lambda slots, ctx: slots.get("username") not in (None, ctx.user_id),
    "software_request":  lambda slots, ctx: (slots.get("software_cost") or 0) > SOFTWARE_COST_LIMIT_IN_DOLLARS,
    "hardware_issue":    lambda slots, ctx: slots.get("severity") == "critical",
    "account_deletion":  lambda slots, ctx: True,
    "access_revocation": lambda slots, ctx: True,
}


def is_dangerous(intent: str, slots: dict, session: SessionState) -> bool:
    """Return True if the intent+slot combination triggers a HITL safety rule."""
    checker = DANGEROUS_ACTIONS.get(intent)
    if checker is None:
        return False
    return bool(checker(slots, session))


def check_authorization(
    requesting_user_id: str,
    target_user_id: str,
    action: str,
    user_roles: list[str],
) -> bool:
    """Return True if the requesting user is allowed to perform the action on the target."""
    if requesting_user_id == target_user_id:
        return True
    if action == "reset_password" and "it_admin" in user_roles:
        return True
    return "admin" in user_roles


def resolve_primary_intent(intents: list[str]) -> str:
    """Pick the highest-priority intent from a multi-intent list."""
    for candidate in INTENT_PRIORITY:
        if candidate in intents:
            return candidate
    return intents[0] if intents else "unknown"
