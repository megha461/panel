"""The credential gate is the part of the realtime transport that can be tested
without a live room. The call path itself is unverified — see the module docstring.
"""

from __future__ import annotations

import pytest

from panel.transports import realtime

ALL_REQUIRED = {
    "LIVEKIT_URL": "wss://example.livekit.cloud",
    "LIVEKIT_API_KEY": "k",
    "LIVEKIT_API_SECRET": "s",
    "DEEPGRAM_API_KEY": "d",
    "CARTESIA_API_KEY": "c",
    "ANTHROPIC_API_KEY": "a",
}


@pytest.fixture
def env(monkeypatch):
    for key in list(realtime.REQUIRED_CREDENTIALS) + [
        v for v in realtime.AVATAR_CREDENTIALS.values()
    ] + ["PANEL_AVATAR"]:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


class TestCredentialGate:
    def test_reports_every_missing_credential_with_a_reason(self, env):
        missing = realtime.missing_credentials()
        assert set(missing) == set(realtime.REQUIRED_CREDENTIALS)
        assert all(reason for reason in missing.values())

    def test_satisfied_when_all_present_and_no_avatar(self, env):
        for key, value in ALL_REQUIRED.items():
            env.setenv(key, value)
        env.setenv("PANEL_AVATAR", "none")
        assert realtime.missing_credentials() == {}
        realtime.check_ready()

    def test_avatar_defaults_to_off_so_no_avatar_key_is_demanded(self, env):
        for key, value in ALL_REQUIRED.items():
            env.setenv(key, value)
        assert realtime.missing_credentials() == {}

    def test_selecting_an_avatar_requires_its_key(self, env):
        for key, value in ALL_REQUIRED.items():
            env.setenv(key, value)
        env.setenv("PANEL_AVATAR", "tavus")

        missing = realtime.missing_credentials()
        assert "TAVUS_API_KEY" in missing

        env.setenv("TAVUS_API_KEY", "t")
        assert realtime.missing_credentials() == {}

    def test_unknown_avatar_provider_is_named_and_options_listed(self, env):
        for key, value in ALL_REQUIRED.items():
            env.setenv(key, value)
        env.setenv("PANEL_AVATAR", "hologram")

        missing = realtime.missing_credentials()
        key = next(k for k in missing if k.startswith("PANEL_AVATAR"))
        assert "tavus" in missing[key] and "none" in missing[key]

    def test_error_names_what_is_missing_and_offers_a_way_forward(self, env):
        with pytest.raises(RuntimeError) as excinfo:
            realtime.check_ready()

        message = str(excinfo.value)
        assert "LIVEKIT_URL" in message
        assert "speech-to-text" in message
        # A blocked user should be told what still works with no credentials.
        assert "panel practice" in message
