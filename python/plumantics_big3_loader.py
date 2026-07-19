"""Top-level script loader for the Big 3 private runtime."""

try:
    import plumantics_big3_runtime  # noqa: F401
except Exception as exc:
    try:
        import sims4.log

        _LOGGER = sims4.log.Logger("Big3RuntimeLoader", default_owner="PlumAntics")
        _LOGGER.exception(
            "Failed importing plumantics_big3_runtime from top-level loader: %s",
            exc,
        )
    except Exception:
        try:
            print(
                "Big3RuntimeLoader import failure for plumantics_big3_runtime: {0}".format(
                    exc
                )
            )
        except Exception:
            pass
