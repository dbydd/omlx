# SPDX-License-Identifier: Apache-2.0
"""The power states section: template, dashboard payload, i18n coverage.

Each state (AC, battery with the lid open, battery with the lid closed)
carries its own mode, idle window, and pinned handling, so the section is
driven by one control group per state rather than one shared pair of fields.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS_TEMPLATE = ROOT / "omlx_web/templates/dashboard/_settings.html"
DASHBOARD_JS = ROOT / "omlx_web/static/js/dashboard.js"

POWER_I18N_KEYS = {
    "settings.advanced.power",
    "settings.advanced.power_check_interval",
    "settings.advanced.power_check_interval_hint",
    "settings.advanced.power_state_serving",
    "settings.advanced.power_state_serving_hint",
    "settings.advanced.power_state_battery",
    "settings.advanced.power_state_battery_hint",
    "settings.advanced.power_state_sealed",
    "settings.advanced.power_state_sealed_hint",
    "settings.advanced.power_mode_resident",
    "settings.advanced.power_mode_on_demand",
    "settings.advanced.power_mode_reject",
    "settings.advanced.power_idle",
    "settings.advanced.power_unload_pinned",
}


def test_settings_template_configures_every_state_independently():
    template = SETTINGS_TEMPLATE.read_text()

    power_start = template.index("<!-- Power subsection -->")
    cache_start = template.index("<!-- Cache subsection -->")
    assert power_start < cache_start

    assert "['serving', 'battery', 'sealed']" in template
    assert 'x-model.number="globalSettings.server.battery_poll_interval"' in template
    assert "globalSettings.server.power_states[state].mode" in template
    assert "globalSettings.server.power_states[state].idle_seconds" in template
    assert "globalSettings.server.power_states[state].unload_pinned" in template
    for mode in ("resident", "on_demand", "reject"):
        assert f'<option value="{mode}"' in template


def test_dashboard_posts_power_states():
    script = DASHBOARD_JS.read_text()
    payload_start = script.index("async saveGlobalSettings()")
    payload_end = script.index("async saveModelSettings()", payload_start)
    payload = script[payload_start:payload_end]

    assert "battery_poll_interval:" in payload
    assert "power_states: this.globalSettings.server.power_states," in payload


def test_power_i18n_keys_exist_in_every_locale():
    i18n_dir = ROOT / "omlx_web/i18n"

    for locale_path in sorted(i18n_dir.glob("*.json")):
        translations = json.loads(locale_path.read_text())
        missing_keys = POWER_I18N_KEYS - translations.keys()
        assert not missing_keys, f"{locale_path.name} is missing {sorted(missing_keys)}"
