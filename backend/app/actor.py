from contextvars import ContextVar

# Propagated from the HTTP middleware into background tasks and explicitly into queue threads.
actor_id: ContextVar[str | None] = ContextVar("eval_actor", default=None)
