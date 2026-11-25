"""The websocket protocol owns the "id" key (it is the message counter): a command field
named id is replaced by an integer before the handler sees it. Edit and delete shipped
broken that way in 0.4.0 ("expected str at 'id'. Got 68")."""
import re
from pathlib import Path

ROOT = Path(__file__).parents[1] / "custom_components" / "garage"


def test_no_websocket_command_takes_a_field_named_id():
    src = (ROOT / "__init__.py").read_text()
    schemas = re.findall(r"websocket_command\(\{(.*?)\}\)", src, re.S)
    assert schemas, "found no websocket schemas to check"
    assert not [s for s in schemas if re.search(r'vol\.(Required|Optional)\("id"\)', s)]


def test_the_panel_never_sends_a_bare_id_to_garage_commands():
    js = (ROOT / "frontend" / "garage-panel.js").read_text()
    calls = re.findall(r"\{ ?type: 'garage/[a-z_]+'[^}]*\}", js)
    assert calls, "found no garage/* calls to check"
    assert not [c for c in calls if re.search(r"[{,]\s*id:", c)]


def test_once_only_registration_is_claimed_before_any_await():
    """Two vehicles set up concurrently. A flag set AFTER an await let both entries into the
    block; the second died on a duplicate route and its vehicle went unavailable."""
    src = (ROOT / "__init__.py").read_text()
    body = src.split("async def _async_register_globals")[1].split("\ndef ")[0]
    for flag in ("_GLOBALS_REGISTERED = True", "_PANEL_REGISTERED = True"):
        guard = body.index("if not " + flag.split(" =")[0] + ":")
        claim = body.index(flag, guard)
        first_await = body.find("await ", guard)
        assert claim < first_await, flag
