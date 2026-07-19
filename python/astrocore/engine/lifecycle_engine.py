from __future__ import annotations


class LifecycleEngine(object):
    def __init__(self, *, registry, state_store, dispatcher):
        self._registry = registry
        self._state_store = state_store
        self._dispatcher = dispatcher

    def dispatch_event(self, event, context):
        applied = []
        for declaration in self._registry.handlers_for_event(event.name):
            result = declaration.handler(context) or {}
            for operation in tuple(result.get("operations", ())):
                applied.append(self._dispatcher.apply(operation))
            if event.sim_id is not None:
                self._state_store.mark_completed(declaration.name, event.name, event.sim_id)

        replayed = self._state_store.pop_due(event.name)
        return {
            "ok": True,
            "applied": tuple(applied),
            "deferred_replayed": len(replayed),
            "replayed": tuple(replayed),
        }
