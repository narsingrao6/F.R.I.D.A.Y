"""
F.R.I.D.A.Y. Task Verifier

Checks whether an executed task appears to have succeeded.

This first version provides a simple verification framework.
Later it can be extended with screen analysis, process checks,
file checks, browser checks, and AI-based verification.
"""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class VerificationResult:
    """Result of verifying an action."""

    success: bool
    message: str
    details: Any = None


class TaskVerifier:
    def __init__(self):
        self._verifiers: dict[str, Callable[..., Any]] = {}

    def register(
        self,
        action: str,
        verifier: Callable[..., Any],
    ) -> None:
        """Register a custom verification function."""

        self._verifiers[action] = verifier

    def verify(
        self,
        action: str,
        result: Any = None,
        **kwargs,
    ) -> VerificationResult:
        """
        Verify an executed action.

        If a custom verifier exists for the action, it is used.
        Otherwise, the executor result is used as a basic signal.
        """

        verifier = self._verifiers.get(action)

        if verifier is not None:
            try:
                verification = verifier(result=result, **kwargs)

                if isinstance(verification, VerificationResult):
                    return verification

                if bool(verification):
                    return VerificationResult(
                        success=True,
                        message=f"Action '{action}' verified successfully.",
                        details=verification,
                    )

                return VerificationResult(
                    success=False,
                    message=f"Action '{action}' could not be verified.",
                    details=verification,
                )

            except Exception as error:
                return VerificationResult(
                    success=False,
                    message=(
                        f"Verification failed for '{action}': "
                        f"{type(error).__name__}: {error}"
                    ),
                )

        # Basic fallback verification.
        if result is None:
            return VerificationResult(
                success=False,
                message=f"No successful result was returned for '{action}'.",
            )

        return VerificationResult(
            success=True,
            message=f"Action '{action}' completed with a result.",
            details=result,
        )

    def has_verifier(self, action: str) -> bool:
        """Check whether a custom verifier exists."""

        return action in self._verifiers

    def actions(self) -> list[str]:
        """Return all actions with registered verifiers."""

        return list(self._verifiers.keys())