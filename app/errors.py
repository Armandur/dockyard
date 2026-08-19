"""Domänfel med HTTP-status och användarvänligt (svenskt) meddelande."""


class DockyardError(Exception):
    status_code = 400

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class SpecError(DockyardError):
    """Ogiltig eller otillåten spec."""
    status_code = 400


class ForbiddenSpec(DockyardError):
    """Spec bryter mot guardrails (namn/registry/skyddat namn)."""
    status_code = 403


class ConflictError(DockyardError):
    """Container med namnet finns redan."""
    status_code = 409


class DockerBackendError(DockyardError):
    """Fel från Docker-motorn/proxyn."""
    status_code = 502


class NotFoundError(DockyardError):
    """Containern som skulle ändras finns inte."""
    status_code = 404
