# SPDX-License-Identifier: Apache-2.0
"""Tests for the power-aware serving states (battery and lid)."""

import asyncio
import time
from unittest.mock import patch

import pytest

from omlx import server
from omlx.engine_pool import EnginePool


class TestPowerState:
    """_power_state combines the power source with the lid."""

    def test_ac_serves_whatever_the_lid_does(self):
        for lid in (True, False, None):
            with (
                patch.object(server, "_on_battery_power", return_value=False),
                patch.object(server, "_lid_is_closed", return_value=lid),
            ):
                assert server._power_state() == server.POWER_SERVING

    def test_battery_open_lid_stops_after_idle(self):
        with (
            patch.object(server, "_on_battery_power", return_value=True),
            patch.object(server, "_lid_is_closed", return_value=False),
        ):
            assert server._power_state() == server.POWER_BATTERY

    def test_battery_closed_lid_seals(self):
        with (
            patch.object(server, "_on_battery_power", return_value=True),
            patch.object(server, "_lid_is_closed", return_value=True),
        ):
            assert server._power_state() == server.POWER_SEALED

    def test_unknown_power_reads_as_unknown(self):
        with patch.object(server, "_on_battery_power", return_value=None):
            assert server._power_state() is None

    def test_unknown_lid_on_battery_is_not_sealed(self):
        """A lid that cannot be read must not be taken for a closed one."""
        with (
            patch.object(server, "_on_battery_power", return_value=True),
            patch.object(server, "_lid_is_closed", return_value=None),
        ):
            assert server._power_state() == server.POWER_BATTERY


class _Entry:
    def __init__(
        self,
        engine="engine",
        is_pinned=False,
        is_loading=False,
        in_use=0,
        last_access=None,
        active=False,
    ):
        self.engine = engine
        self.is_pinned = is_pinned
        self.is_loading = is_loading
        self.in_use = in_use
        self.last_access = time.time() if last_access is None else last_access
        self._active = active
        self.model_id = "m"
        self.model_format = None


class _Pool:
    """Enough of EnginePool to drive unload_for_battery and the pause gate."""

    def __init__(self, entries):
        self._entries = entries
        self._paused = False
        self.unloaded = []

    async def unload_if_idle_unpinned(self, model_id):
        self.unloaded.append(model_id)
        return True

    async def _unload_engine(self, model_id):
        self.unloaded.append(model_id)

    def _entry_has_active_requests(self, entry):
        return entry._active


def _run(pool, idle, include_pinned=False):
    return asyncio.run(
        EnginePool.unload_for_battery(pool, idle, include_pinned=include_pinned)
    )


class TestUnloadForBattery:
    def test_unpinned_idle_unloads_only_past_the_window(self):
        now = time.time()
        pool = _Pool(
            {
                "idle": _Entry(last_access=now - 121),
                "recent": _Entry(last_access=now - 119),
            }
        )
        assert _run(pool, 120) == ["idle"]

    def test_busy_and_loading_entries_stay(self):
        now = time.time()
        pool = _Pool(
            {
                "busy": _Entry(last_access=now - 600, in_use=1),
                "loading": _Entry(last_access=now - 600, is_loading=True),
                "gone": _Entry(engine=None, last_access=now - 600),
            }
        )
        assert _run(pool, 120) == []

    def test_pinned_stays_unless_asked_for(self):
        now = time.time()
        pool = _Pool({"pinned": _Entry(last_access=now - 600, is_pinned=True)})
        assert _run(pool, 120) == []
        assert _run(pool, 120, include_pinned=True) == ["pinned"]

    def test_pinned_in_use_still_stays(self):
        """Even sealed, a pinned model mid-request finishes first."""
        now = time.time()
        pool = _Pool(
            {"pinned-busy": _Entry(last_access=now - 600, is_pinned=True, active=True)}
        )
        assert _run(pool, 0.0, include_pinned=True) == []


class _Gate(EnginePool):
    """EnginePool with only what get_engine needs for the pause gate."""

    def __init__(self):
        self._paused = False
        self._entries = {"m": _Entry()}
        self._lock = asyncio.Lock()
        self._settings_manager = None

    async def _reloadable_failed_engine(self, model_id):
        return None

    def _acquire_loaded_engine(self, *args, **kwargs):
        return None


class TestPauseGate:
    def test_paused_refuses_a_new_load(self):
        from omlx.exceptions import ModelBusyError

        pool = _Gate()
        pool.set_paused(True)
        assert pool.paused is True
        with pytest.raises(ModelBusyError):
            asyncio.run(pool.get_engine("m"))

    def test_unpaused_is_ready_to_load(self):
        pool = _Gate()
        pool.set_paused(False)
        assert pool.paused is False


class _Settings:
    """Stand-in for ServerSettings: the policy reads power_states only."""

    def __init__(self, power_states=None):
        if power_states is not None:
            self.power_states = power_states


class TestPowerPolicy:
    """_power_policy maps a state to mode, idle window, and pinned handling.

    The mode is what the serving loop acts on: reject pauses the pool and
    unloads, on_demand unloads, resident leaves loaded models alone.
    """

    def test_defaults_per_state(self):
        empty = _Settings({})
        assert server._power_policy(empty, server.POWER_SERVING) == (
            "resident",
            900.0,
            False,
        )
        assert server._power_policy(empty, server.POWER_BATTERY) == (
            "reject",
            120.0,
            True,
        )
        assert server._power_policy(empty, server.POWER_SEALED) == (
            "reject",
            0.0,
            True,
        )

    def test_missing_power_states_falls_back(self):
        """A settings object without the key, or no object at all."""
        assert server._power_policy(_Settings(), server.POWER_BATTERY) == (
            "reject",
            120.0,
            True,
        )
        assert server._power_policy(None, server.POWER_SEALED) == (
            "reject",
            0.0,
            True,
        )
        assert server._power_policy(
            _Settings(["not", "a", "dict"]), server.POWER_SERVING
        ) == (
            "resident",
            900.0,
            False,
        )

    def test_configured_values_win(self):
        settings = _Settings(
            {
                "serving": {
                    "mode": "on_demand",
                    "idle_seconds": 300,
                    "unload_pinned": True,
                },
                "battery": {
                    "mode": "resident",
                    "idle_seconds": 60,
                    "unload_pinned": False,
                },
                "sealed": {
                    "mode": "on_demand",
                    "idle_seconds": 0,
                    "unload_pinned": True,
                },
            }
        )
        assert server._power_policy(settings, server.POWER_SERVING) == (
            "on_demand",
            300.0,
            True,
        )
        assert server._power_policy(settings, server.POWER_BATTERY) == (
            "resident",
            60.0,
            False,
        )
        assert server._power_policy(settings, server.POWER_SEALED) == (
            "on_demand",
            0.0,
            True,
        )

    def test_partial_and_bad_entries_keep_the_default(self):
        settings = _Settings(
            {
                "battery": {"mode": "nonsense"},
                "sealed": {"idle_seconds": "soon", "unload_pinned": "yes"},
            }
        )
        assert server._power_policy(settings, server.POWER_BATTERY) == (
            "reject",
            120.0,
            True,
        )
        assert server._power_policy(settings, server.POWER_SEALED) == (
            "reject",
            0.0,
            True,
        )

    def test_negative_idle_clamps_and_ac_need_not_unload_pinned(self):
        settings = _Settings(
            {
                "battery": {"mode": "on_demand", "idle_seconds": -30},
                "sealed": {"unload_pinned": False},
            }
        )
        assert server._power_policy(settings, server.POWER_BATTERY) == (
            "on_demand",
            0.0,
            True,
        )
        assert server._power_policy(settings, server.POWER_SEALED) == (
            "reject",
            0.0,
            False,
        )


class _RecordingPool:
    """Records what the serving loop asks the pool to do."""

    def __init__(self):
        self.paused = None
        self.unload_calls = []

    def set_paused(self, paused: bool) -> None:
        self.paused = paused

    async def unload_for_battery(self, idle_seconds, include_pinned=False):
        self.unload_calls.append((idle_seconds, include_pinned))
        return ["idle-model"]


class TestApplyPowerPolicy:
    """The mode decides the pool action: pause, unload, or leave alone."""

    @staticmethod
    def _apply(pool, power_states, state):
        return asyncio.run(
            server._apply_power_policy(pool, _Settings(power_states), state)
        )

    def test_reject_pauses_and_unloads_including_pinned(self):
        pool = _RecordingPool()
        mode, idle, unloaded = self._apply(
            pool,
            {
                "battery": {
                    "mode": "reject",
                    "idle_seconds": 30,
                    "unload_pinned": True,
                }
            },
            server.POWER_BATTERY,
        )
        assert (mode, idle) == ("reject", 30.0)
        assert pool.paused is True
        assert pool.unload_calls == [(30.0, True)]
        assert unloaded == ["idle-model"]

    def test_on_demand_unloads_without_pausing(self):
        pool = _RecordingPool()
        mode, idle, _unloaded = self._apply(
            pool,
            {
                "serving": {
                    "mode": "on_demand",
                    "idle_seconds": 600,
                    "unload_pinned": False,
                }
            },
            server.POWER_SERVING,
        )
        assert (mode, idle) == ("on_demand", 600.0)
        assert pool.paused is False
        assert pool.unload_calls == [(600.0, False)]

    def test_resident_leaves_models_to_their_own_ttl(self):
        pool = _RecordingPool()
        mode, _idle, unloaded = self._apply(pool, {}, server.POWER_SERVING)
        assert mode == "resident"
        assert pool.paused is False
        assert pool.unload_calls == []
        assert unloaded == []

    def test_sealed_default_unloads_everything_at_once(self):
        pool = _RecordingPool()
        mode, idle, _unloaded = self._apply(pool, {}, server.POWER_SEALED)
        assert (mode, idle) == ("reject", 0.0)
        assert pool.paused is True
        assert pool.unload_calls == [(0.0, True)]
