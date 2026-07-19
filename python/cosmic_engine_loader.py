"""Top-level script loader for Cosmic Engine runtime package."""

_BOOTSTRAP_CALLBACKS_REGISTERED = False
_RUNTIME_INSTALL_SUCCEEDED = False
_INSTALL_RETRY_HANDLE = None


class _LoaderAlarmOwner(object):
    pass


_LOADER_ALARM_OWNER = _LoaderAlarmOwner()


def _get_logger():
    try:
        import sims4.log  # type: ignore

        return sims4.log.Logger("CosmicEngineLoader", default_owner="PlumAntics")
    except Exception:
        return None


def _log_exception(message, exc):
    logger = _get_logger()
    if logger is not None:
        try:
            logger.exception(message, exc)
            return
        except Exception:
            pass
    try:
        print("{0}: {1}".format(message, exc))
    except Exception:
        pass


def _log_debug(message, *args):
    logger = _get_logger()
    if logger is None:
        return
    try:
        logger.debug(message, *args)
    except Exception:
        pass


def _cancel_install_retry():
    global _INSTALL_RETRY_HANDLE

    if _INSTALL_RETRY_HANDLE is None:
        return False
    try:
        import alarms  # type: ignore

        alarms.cancel_alarm(_INSTALL_RETRY_HANDLE)
    except Exception:
        pass
    _INSTALL_RETRY_HANDLE = None
    return True


def _runtime_status_is_ready(cosmic_engine):
    try:
        get_runtime_status_payload = getattr(cosmic_engine, "get_runtime_status_payload", None)
        if not callable(get_runtime_status_payload):
            return False
        payload = get_runtime_status_payload() or {}
    except Exception:
        return False

    return bool(payload.get("initialized"))


def _attempt_runtime_install():
    global _RUNTIME_INSTALL_SUCCEEDED

    if _RUNTIME_INSTALL_SUCCEEDED:
        return True

    try:
        import cosmic_engine
    except Exception as exc:
        _log_exception("Failed importing cosmic_engine package", exc)
        return False

    try:
        register_debug_commands = getattr(cosmic_engine, "register_debug_commands", None)
        if callable(register_debug_commands):
            register_debug_commands()

        if not _runtime_status_is_ready(cosmic_engine):
            force_runtime_install_now = getattr(cosmic_engine, "force_runtime_install_now", None)
            if callable(force_runtime_install_now):
                force_runtime_install_now()
            else:
                install_runtime_hooks = getattr(cosmic_engine, "install_runtime_hooks", None)
                if callable(install_runtime_hooks):
                    install_runtime_hooks()
        _RUNTIME_INSTALL_SUCCEEDED = _runtime_status_is_ready(cosmic_engine)
    except Exception as exc:
        _log_exception("Failed registering Cosmic Engine runtime/debug hooks", exc)
        return False

    if _RUNTIME_INSTALL_SUCCEEDED:
        _cancel_install_retry()
    return _RUNTIME_INSTALL_SUCCEEDED


def _bootstrap_runtime_install(*_args, **_kwargs):
    del _args
    del _kwargs
    if _attempt_runtime_install():
        _log_debug("Cosmic Engine runtime bootstrap succeeded.")
    else:
        _schedule_install_retry()


def _register_bootstrap_callbacks():
    global _BOOTSTRAP_CALLBACKS_REGISTERED

    if _BOOTSTRAP_CALLBACKS_REGISTERED:
        return True

    try:
        import sims4.callback_utils as callback_utils  # type: ignore
    except Exception:
        return False

    callback_event = getattr(callback_utils, "CallbackEvent", None)
    add_callbacks = getattr(callback_utils, "add_callbacks", None)
    if callback_event is None or not callable(add_callbacks):
        return False

    registered_any = False
    for name in ("GAMEPLAY_SERVICES_STARTED", "POST_ZONE_LOAD", "ZONE_RUNNING"):
        event_value = getattr(callback_event, name, None)
        if event_value is None:
            continue
        try:
            add_callbacks(event_value, _bootstrap_runtime_install)
            registered_any = True
        except Exception:
            continue

    _BOOTSTRAP_CALLBACKS_REGISTERED = registered_any
    return registered_any


def _schedule_install_retry(interval_real_seconds=5):
    global _INSTALL_RETRY_HANDLE

    if _RUNTIME_INSTALL_SUCCEEDED:
        _cancel_install_retry()
        return True
    if _INSTALL_RETRY_HANDLE is not None:
        return True

    try:
        import alarms  # type: ignore
    except Exception:
        return False

    add_real_time = getattr(alarms, "add_alarm_real_time", None)
    if callable(add_real_time):
        try:
            import clock  # type: ignore

            interval = clock.interval_in_real_seconds(max(1, int(interval_real_seconds)))
            _INSTALL_RETRY_HANDLE = add_real_time(
                _LOADER_ALARM_OWNER,
                interval,
                _bootstrap_runtime_install,
                repeating=False,
            )
            return True
        except Exception:
            _INSTALL_RETRY_HANDLE = None

    try:
        import clock  # type: ignore

        _INSTALL_RETRY_HANDLE = alarms.add_alarm(
            _LOADER_ALARM_OWNER,
            clock.interval_in_sim_minutes(1),
            _bootstrap_runtime_install,
            repeating=False,
        )
        return True
    except Exception:
        _INSTALL_RETRY_HANDLE = None
        return False


_attempt_runtime_install()
_register_bootstrap_callbacks()
_schedule_install_retry()
