from __future__ import annotations

import asyncio

import voluptuous as vol
from homeassistant.components.infrared import (
    InfraredReceivedSignal,
    async_get_receivers,
    async_subscribe_receiver,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

from .const import (
    CONF_FINGERPRINT,
    CONF_NAME,
    CONF_RECEIVER,
    DEFAULT_DEBOUNCE_WINDOW,
    DEFAULT_DOUBLE_CLICK_WINDOW,
    DEFAULT_IMMEDIATE_SINGLE,
    DEFAULT_LEARN_TIMEOUT,
    DEFAULT_NEW_PRESS_WINDOW,
    DOMAIN,
    OPT_DEBOUNCE_WINDOW,
    OPT_DOUBLE_CLICK_WINDOW,
    OPT_IMMEDIATE_SINGLE,
    OPT_LEARN_TIMEOUT,
    OPT_NEW_PRESS_WINDOW,
)
from .engine import fingerprint as compute_fingerprint, suggest_name


class IrRemoteConfigFlow(ConfigFlow, domain=DOMAIN):
    """Pick an infrared receiver entity and name the remote."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        if not async_get_receivers(self.hass):
            return self.async_abort(reason="no_infrared_receivers")

        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_RECEIVER])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Required(CONF_RECEIVER): EntitySelector(
                        EntitySelectorConfig(domain="infrared")
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> IrRemoteOptionsFlow:
        return IrRemoteOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {"button": LearnButtonSubentryFlow}


class IrRemoteOptionsFlow(OptionsFlow):
    """Tune timing windows and click behaviour for a configured remote."""

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        opts = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        OPT_DEBOUNCE_WINDOW,
                        default=opts.get(OPT_DEBOUNCE_WINDOW, DEFAULT_DEBOUNCE_WINDOW),
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.05, max=1.0)),
                    vol.Optional(
                        OPT_NEW_PRESS_WINDOW,
                        default=opts.get(
                            OPT_NEW_PRESS_WINDOW, DEFAULT_NEW_PRESS_WINDOW
                        ),
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=2.0)),
                    vol.Optional(
                        OPT_DOUBLE_CLICK_WINDOW,
                        default=opts.get(
                            OPT_DOUBLE_CLICK_WINDOW, DEFAULT_DOUBLE_CLICK_WINDOW
                        ),
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.3, max=5.0)),
                    vol.Optional(
                        OPT_LEARN_TIMEOUT,
                        default=opts.get(OPT_LEARN_TIMEOUT, DEFAULT_LEARN_TIMEOUT),
                    ): vol.All(vol.Coerce(float), vol.Range(min=5.0, max=120.0)),
                    vol.Optional(
                        OPT_IMMEDIATE_SINGLE,
                        default=opts.get(
                            OPT_IMMEDIATE_SINGLE, DEFAULT_IMMEDIATE_SINGLE
                        ),
                    ): bool,
                }
            ),
        )


class LearnButtonSubentryFlow(ConfigSubentryFlow):
    """Learn one IR button via two matching captures, then name it.

    Flow:
      1. user    (progress) — first press; waits for signal + debounce silence
      2. ready   (form)     — explicit "Continue when ready" before second press
      3. confirm (progress) — second press; must match first fingerprint
      4. name    (form)     — name the confirmed button
      Branches: mismatch (form) on fingerprint disagreement; timeout (form) on no signal.
    """

    _capture_task: asyncio.Task[str] | None = None
    _first_fingerprint: str | None = None
    _fingerprint: str | None = None

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> SubentryFlowResult:
        """First press — listen until a signal settles, then pause for user."""
        if self._capture_task is None:
            self._first_fingerprint = None
            self._capture_task = self.hass.async_create_task(self._async_capture())

        if not self._capture_task.done():
            return self.async_show_progress(
                step_id="user",
                progress_action="press_button",
                progress_task=self._capture_task,
            )

        try:
            self._first_fingerprint = self._capture_task.result()
        except TimeoutError:
            self._capture_task = None
            return self.async_show_progress_done(next_step_id="timeout")
        except Exception:
            self._capture_task = None
            return self.async_abort(reason="capture_failed")

        self._capture_task = None
        return self.async_show_progress_done(next_step_id="ready")

    async def async_step_ready(
        self, user_input: dict | None = None
    ) -> SubentryFlowResult:
        """Pause — user confirms they're ready before the second press begins."""
        if user_input is not None:
            return await self.async_step_confirm()
        return self.async_show_form(step_id="ready", data_schema=vol.Schema({}))

    async def async_step_confirm(
        self, user_input: dict | None = None
    ) -> SubentryFlowResult:
        """Second press — must settle to the same fingerprint as the first."""
        if self._capture_task is None:
            self._capture_task = self.hass.async_create_task(self._async_capture())

        if not self._capture_task.done():
            return self.async_show_progress(
                step_id="confirm",
                progress_action="press_button_again",
                progress_task=self._capture_task,
            )

        try:
            second_fp = self._capture_task.result()
        except TimeoutError:
            self._capture_task = None
            return self.async_show_progress_done(next_step_id="timeout")
        except Exception:
            self._capture_task = None
            return self.async_abort(reason="capture_failed")

        self._capture_task = None

        if second_fp != self._first_fingerprint:
            return self.async_show_progress_done(next_step_id="mismatch")

        self._fingerprint = second_fp
        return self.async_show_progress_done(next_step_id="name")

    async def async_step_mismatch(
        self, user_input: dict | None = None
    ) -> SubentryFlowResult:
        """The two presses didn't match — offer to start over."""
        if user_input is not None:
            self._capture_task = None
            self._first_fingerprint = None
            return await self.async_step_user()
        return self.async_show_form(step_id="mismatch", data_schema=vol.Schema({}))

    async def async_step_name(
        self, user_input: dict | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={
                    CONF_FINGERPRINT: self._fingerprint,
                    CONF_NAME: user_input[CONF_NAME],
                },
            )

        suggested = suggest_name(self._fingerprint)
        return self.async_show_form(
            step_id="name",
            data_schema=vol.Schema(
                {vol.Required(CONF_NAME, default=suggested): str}
            ),
        )

    async def async_step_timeout(
        self, user_input: dict | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._capture_task = None
            return await self.async_step_user()
        return self.async_show_form(step_id="timeout", data_schema=vol.Schema({}))

    async def _async_capture(self) -> str:
        """Subscribe to the receiver and return the first stable fingerprint.

        Captures the very first signal that arrives after a debounce_window gap.
        IR remotes send the full initial frame first, then shorter repeat frames
        every ~110 ms while held. By resolving on the first signal (not the last),
        we always capture the complete initial frame — repeat frames are dropped
        by the debounce check. The configured debounce_window is used so the
        behaviour matches what the user has tuned for their hardware.
        """
        entry = self._get_entry()
        receiver_id: str = entry.data[CONF_RECEIVER]
        learn_timeout: float = entry.options.get(OPT_LEARN_TIMEOUT, DEFAULT_LEARN_TIMEOUT)
        debounce: float = entry.options.get(OPT_DEBOUNCE_WINDOW, DEFAULT_DEBOUNCE_WINDOW)

        fut: asyncio.Future[str] = self.hass.loop.create_future()
        last_t: float = 0.0

        @callback
        def on_signal(signal: InfraredReceivedSignal) -> None:
            nonlocal last_t
            now = self.hass.loop.time()
            if now - last_t < debounce:
                last_t = now
                return
            last_t = now
            if not fut.done():
                fut.set_result(compute_fingerprint(signal.timings))

        unsub = async_subscribe_receiver(self.hass, receiver_id, on_signal)
        try:
            async with asyncio.timeout(learn_timeout):
                return await fut
        finally:
            unsub()
