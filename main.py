"""CLI entry point — starts the interactive IT support agent loop."""

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from agent.failure import FAILURE_MESSAGES, FailureMode, detect_failure, failure_to_policy
from agent.session import SessionStore
from classifier.llm_classifier import classify_intent
from classifier.providers.factory import get_provider
from logs.logger import log_session_end, log_session_start, log_user_input
from models.policy import ResponsePolicy

load_dotenv()
console = Console()
store = SessionStore()

WELCOME = """[bold cyan]Smart IT Support Agent[/bold cyan]
Type your request in plain English. Type [bold]exit[/bold] to quit.
─────────────────────────────────────────
Supported requests:
  • Reset a system password
  • Check leave balance
  • Request software
  • Look up a company policy
  • Report a hardware issue"""

_POLICY_COLOUR = {
    ResponsePolicy.ANSWER:   "green",
    ResponsePolicy.CLARIFY:  "yellow",
    ResponsePolicy.REDIRECT: "red",
    ResponsePolicy.DENY:     "red",
    ResponsePolicy.ESCALATE: "magenta",
}


def _respond(intent_result, policy: ResponsePolicy) -> str:
    """Build the Rich-formatted display text for a given intent result and response policy."""
    if policy == ResponsePolicy.ANSWER:
        parts = [f"Intent: [bold]{intent_result.intent}[/bold]"]
        if intent_result.slots:
            slots_str = ", ".join(f"{k}={v}" for k, v in intent_result.slots.items())
            parts.append(f"Slots: {slots_str}")
        parts.append("\n[dim](Phase 2 — tool execution coming in Phase 3)[/dim]")
        return "\n".join(parts)

    if policy == ResponsePolicy.CLARIFY:
        missing = ", ".join(intent_result.missing_slots)
        return (
            f"{FAILURE_MESSAGES[FailureMode.MISSING_SLOTS]}\n"
            f"Missing: [bold]{missing}[/bold]"
        )

    failure = detect_failure(intent_result)
    if failure and failure in FAILURE_MESSAGES:
        return FAILURE_MESSAGES[failure]

    return "I can only help with IT support requests."


def main() -> None:
    """Run the interactive IT support agent until the user types exit."""
    provider = get_provider()
    console.print(Panel(WELCOME, border_style="cyan"))
    console.print(f"[dim]Provider: {provider.provider_name()} ({provider.model_name()})[/dim]\n")

    user_id = Prompt.ask("[bold]Your user ID[/bold]")
    session_id = f"sess_{user_id}"
    session = store.get_or_create(session_id, user_id)
    log_session_start(session_id, user_id, provider.provider_name())

    console.print(f"[dim]Session started: {session_id}[/dim]\n")

    while True:
        user_input = Prompt.ask("[bold green]You[/bold green]").strip()

        if user_input.lower() in ("exit", "quit", "q"):
            log_session_end(session_id, user_id, session.turn_count)
            console.print("[dim]Session ended. Goodbye.[/dim]")
            break

        if not user_input:
            continue

        session.turn_count += 1
        store.update(session_id, session)
        log_user_input(session_id, user_id, session.turn_count, user_input)

        result = classify_intent(user_input, session, provider)

        failure = detect_failure(result)
        if failure:
            policy = failure_to_policy(failure)
        elif result.intent == "unknown":
            policy = ResponsePolicy.REDIRECT
        else:
            policy = ResponsePolicy.ANSWER

        colour = _POLICY_COLOUR.get(policy, "white")
        response_text = _respond(result, policy)

        console.print(
            Panel(
                response_text,
                title=f"[{colour}]{policy.upper()}[/{colour}]  "
                      f"[dim]conf={result.confidence:.2f}[/dim]",
                border_style=colour,
            )
        )


if __name__ == "__main__":
    main()
