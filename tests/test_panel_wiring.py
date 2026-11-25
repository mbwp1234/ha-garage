"""The panel is plain JS with no test runner here, so these read its source: a feature that is
written but never wired (no click handler, no sheet branch) is the failure they catch."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[1] / "custom_components" / "garage"
JS = (ROOT / "frontend" / "garage-panel.js").read_text()
INIT = (ROOT / "__init__.py").read_text()


def test_vehicle_switcher_is_drawn_and_handled():
    assert "this._tabs(d)" in JS and "_tabs(d) {" in JS
    assert "a === 'veh'" in JS and "this._entry = id" in JS
    assert '"summary": {k: r.summary.get(k, 0) for k in ("over", "soon", "nolog")}' in INIT


def test_typed_mileage_is_wired_end_to_end():
    assert "a === 'odo'" in JS and "a === 'odosave'" in JS
    assert "s.kind === 'odo' ? this._odoSheet()" in JS
    assert "type: 'garage/set_odometer'" in JS
    assert '"garage/set_odometer"' in INIT and "register_command(hass, ws_odometer)" in INIT


def test_picture_tile_follows_the_theme():
    rule = re.search(r"'\.garage\{[^']*\}'", JS).group(0)
    assert "var(--imgbg)" in rule and "#0B0F16" not in rule
    assert JS.count("--imgbg:") == 2      # one per theme


def test_month_limits_are_shown_where_intervals_are():
    assert JS.count("st.months ?") >= 2


def test_new_vehicle_hero_never_says_all_good():
    assert "never logged" in JS and "var fresh0 =" in JS


def test_every_label_fits_the_list_column():
    # "Rear diff ch…": a truncated label is a missing label. The Tacoma's longest short is 12.
    for f in (ROOT / "schedules").glob("*.json"):
        for it in json.loads(f.read_text())["items"]:
            assert len(it["short"]) <= 12, (f.name, it["short"])


def test_dashboard_deep_link_switches_vehicle_on_navigation():
    assert "window.addEventListener('location-changed', this._onNav)" in JS
    assert "removeEventListener('location-changed', this._onNav)" in JS
    assert "_fromUrl() {" in JS and JS.count("._fromUrl()") >= 2


def test_header_renders_before_any_data():
    """HA sets `narrow` before garage/get answers, so the header (and its tabs) renders with
    no data. v0.7.0-0.7.1 read d.vehicles off null there and the panel never opened."""
    body = JS.split("_tabs(d) {")[1].split("\n  }\n")[0]
    assert "(d && d.vehicles)" in body and "d && d.vehicle && d.vehicle.entry_id" in body


def test_harness_sets_hass_before_narrow_like_home_assistant():
    shoot = (ROOT.parents[1] / "dev" / "shoot.py").read_text()
    assert "el.hass = hass; el.narrow = __NARROW__;" in shoot
