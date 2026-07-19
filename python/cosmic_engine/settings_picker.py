"""Custom picker-backed settings launcher for Simstrology self-menu options."""

from __future__ import annotations

try:
    from interactions import ParticipantType  # type: ignore
    from interactions.base.picker_interaction import PickerSuperInteraction  # type: ignore
    from interactions.utils.tunable import TunableContinuation  # type: ignore
    from sims4.localization import TunableLocalizedStringFactory  # type: ignore
    from sims4.tuning.tunable import OptionalTunable, TunableList, TunableTuple  # type: ignore
    from sims4.tuning.tunable_base import GroupNames  # type: ignore
    from sims4.utils import flexmethod  # type: ignore
    from ui.ui_dialog_picker import UiItemPicker, BasePickerRow  # type: ignore
except Exception:  # pragma: no cover - local fallback shims
    class _SimpleTunable(object):
        def __init__(self, *args, **kwargs):
            pass

    class ParticipantType(object):
        Actor = "Actor"
        Object = "Object"

    class PickerSuperInteraction(object):
        INSTANCE_TUNABLES = {}

        def _show_picker_dialog(self, *args, **kwargs):
            return None

        def push_tunable_continuation(self, continuation):
            self._last_continuation = continuation
            return True

        @classmethod
        def create_localized_string(cls, value, *args, **kwargs):
            return value

    class TunableContinuation(_SimpleTunable):
        pass

    class TunableLocalizedStringFactory(_SimpleTunable):
        pass

    class OptionalTunable(_SimpleTunable):
        pass

    class TunableList(_SimpleTunable):
        pass

    class TunableTuple(_SimpleTunable):
        pass

    class GroupNames(object):
        PICKERTUNING = "picker"

    def flexmethod(fn):
        return fn

    class UiItemPicker(object):
        @staticmethod
        def TunableFactory(*args, **kwargs):
            return None

    class BasePickerRow(object):
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)


class CosmicEngineSettingsPickerInteraction(PickerSuperInteraction):
    """Minimal picker that forwards row selections to existing interactions."""

    INSTANCE_TUNABLES = {
        "picker_dialog": UiItemPicker.TunableFactory(
            description="The item picker dialog for Simstrology settings.",
            tuning_group=GroupNames.PICKERTUNING,
        ),
        "choices": TunableList(
            description="Rows shown in the Simstrology settings picker.",
            tuning_group=GroupNames.PICKERTUNING,
            tunable=TunableTuple(
                item_name=OptionalTunable(
                    description="The displayed row label.",
                    tunable=TunableLocalizedStringFactory(
                        description="The displayed row label."
                    ),
                ),
                item_description=OptionalTunable(
                    description="Optional description shown under the row.",
                    tunable=TunableLocalizedStringFactory(
                        description="Optional row description."
                    ),
                ),
                item_tooltip=OptionalTunable(
                    description="Optional tooltip shown for the row.",
                    tunable=TunableLocalizedStringFactory(
                        description="Optional row tooltip."
                    ),
                ),
                continuation=TunableContinuation(
                    description="Continuation pushed when this row is selected.",
                    locked_args={
                        "actor": ParticipantType.Actor,
                        "target": ParticipantType.Object,
                    },
                ),
            ),
        ),
    }

    def _run_interaction_gen(self, timeline):
        target = getattr(self, "target", None)
        self._show_picker_dialog(target, target_sim=target)
        return True

    @classmethod
    def _materialize_localized_text(cls, value, default=None):
        if value is None:
            return default
        if callable(value):
            try:
                return value()
            except TypeError:
                pass
            except Exception:
                return default
        try:
            return cls.create_localized_string(value)
        except Exception:
            return default

    @flexmethod
    def picker_rows_gen(cls, inst, target, context, **kwargs):
        inst_or_cls = inst if inst is not None else cls
        for choice in tuple(getattr(inst_or_cls, "choices", ()) or ()):
            name = inst_or_cls._materialize_localized_text(
                getattr(choice, "item_name", None),
                default="",
            )
            description_factory = getattr(choice, "item_description", None)
            tooltip_factory = getattr(choice, "item_tooltip", None)
            row_description = inst_or_cls._materialize_localized_text(
                description_factory,
                default=None,
            )
            tooltip_text = inst_or_cls._materialize_localized_text(
                tooltip_factory,
                default=None,
            )
            row_tooltip = (
                (lambda *_, _tooltip=tooltip_text, **__: _tooltip)
                if tooltip_text is not None
                else None
            )
            yield BasePickerRow(
                is_enable=True,
                name=name,
                row_description=row_description,
                row_tooltip=row_tooltip,
                tag=choice,
            )

    def on_choice_selected(self, choice_tag, **kwargs):
        if choice_tag is None:
            return
        continuation = getattr(choice_tag, "continuation", None)
        if continuation:
            self.push_tunable_continuation(continuation)


class SimstrologyHubPickerInteraction(CosmicEngineSettingsPickerInteraction):
    """Navigation picker used by the primary Simstrology Hub launcher.

    This deliberately shares the stable continuation implementation used by
    the settings pickers.  Keeping navigation in Python gives the hub one
    extensible home for future state-aware rows without duplicating any chart,
    transit, onboarding, or cheat behavior here.
    """

    pass
