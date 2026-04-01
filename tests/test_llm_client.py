import os
import unittest
from unittest.mock import patch

from llm_client import (
    DEFAULT_LITELLM_API_BASE,
    DEFAULT_LITELLM_CURATOR_MODEL,
    credential_env_name,
    credentials_available,
    resolve_api_base,
    resolve_model,
    resolve_provider,
)


class LLMClientEnvResolutionTests(unittest.TestCase):
    def test_defaults_to_gemini_provider(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_provider("summarizer"), "gemini")

    def test_task_specific_provider_override_wins(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "gemini",
                "LLM_SUMMARIZER_PROVIDER": "litellm",
            },
            clear=True,
        ):
            self.assertEqual(resolve_provider("summarizer"), "litellm")

    def test_litellm_task_model_override_wins(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "litellm",
                "LITELLM_MODEL": "shared-model",
                "LITELLM_CURATOR_MODEL": "curator-model",
            },
            clear=True,
        ):
            self.assertEqual(resolve_model("curator"), "curator-model")

    def test_litellm_shared_model_used_when_task_override_missing(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "litellm",
                "LITELLM_MODEL": "shared-model",
            },
            clear=True,
        ):
            self.assertEqual(resolve_model("summarizer"), "shared-model")

    def test_litellm_default_model_used_when_env_missing(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "litellm",
            },
            clear=True,
        ):
            self.assertEqual(resolve_model("curator"), DEFAULT_LITELLM_CURATOR_MODEL)

    def test_litellm_credentials_can_come_from_keychain(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "litellm",
            },
            clear=True,
        ):
            with patch("llm_client._litellm_keychain_secret", return_value="secret-from-keychain"):
                self.assertTrue(credentials_available("summarizer"))

    def test_provider_credential_name(self) -> None:
        self.assertEqual(credential_env_name("gemini"), "GEMINI_API_KEY")
        self.assertEqual(credential_env_name("litellm"), "LITELLM_API_KEY")

    def test_litellm_api_base_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_api_base("litellm"), DEFAULT_LITELLM_API_BASE)


if __name__ == "__main__":
    unittest.main()
