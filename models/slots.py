"""Per-intent slot schemas and required/optional slot registries."""

from typing import Literal

from pydantic import BaseModel


class ResetPasswordSlots(BaseModel):
    """Slots for a password reset request."""

    system_name: str
    username: str | None = None  # defaults to session user_id if not provided


class CheckLeaveSlots(BaseModel):
    """Slots for a leave balance inquiry."""

    leave_type: Literal["sick", "vacation", "personal", "maternity", "paternity", "other"]
    date_range: str | None = None


class SoftwareRequestSlots(BaseModel):
    """Slots for a software installation or access request."""

    software_name: str
    reason: str
    urgency: Literal["low", "medium", "high"] | None = "medium"
    software_cost: float | None = None  # populated by tool lookup, not user input


class PolicyLookupSlots(BaseModel):
    """Slots for a company policy lookup."""

    topic: str


class HardwareIssueSlots(BaseModel):
    """Slots for a hardware fault report."""

    device_id: str | None = None  # inferred from user asset list
    description: str
    severity: Literal["low", "medium", "high", "critical"] | None = "medium"


REQUIRED_SLOTS: dict[str, list[str]] = {
    "reset_password":   ["system_name"],
    "check_leave":      ["leave_type"],
    "software_request": ["software_name", "reason"],
    "policy_lookup":    ["topic"],
    "hardware_issue":   ["description"],
}

OPTIONAL_SLOTS: dict[str, list[str]] = {
    "reset_password":   ["username"],
    "check_leave":      ["date_range"],
    "software_request": ["urgency"],
    "policy_lookup":    [],
    "hardware_issue":   ["device_id", "severity"],
}
