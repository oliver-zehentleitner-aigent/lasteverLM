import pytest
from lasteverlm_core import ConfigError

from lasteverlm_rag.config import Settings

from .conftest import BASE_ENV


def test_settings_refuse_a_configured_model_without_price():
    """Pricing itself is core's; this checks that rag refuses to start without it."""
    with pytest.raises(ConfigError, match="test-llm"):
        Settings.from_env({**BASE_ENV, "DEMO_TOKEN": "d", "MODEL_PRICES": ""})
    with pytest.raises(ConfigError, match="tts-1"):
        Settings.from_env({**BASE_ENV, "DEMO_TOKEN": "d", "TTS_MODEL": "tts-1"})
    with pytest.raises(ConfigError):
        Settings.from_env({**BASE_ENV, "DEMO_TOKEN": "d", "MODEL_PRICES": "[1]"})
