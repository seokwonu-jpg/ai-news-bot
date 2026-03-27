import os

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_CURATOR_MODEL = "gemini-2.5-flash-lite"
DEFAULT_SUMMARIZER_MODEL = "gemini-2.5-flash"

_TASK_DEFAULTS = {
    "curator": DEFAULT_CURATOR_MODEL,
    "summarizer": DEFAULT_SUMMARIZER_MODEL,
}

_TASK_ENV_VARS = {
    "curator": "GEMINI_CURATOR_MODEL",
    "summarizer": "GEMINI_SUMMARIZER_MODEL",
}


def resolve_gemini_model(task: str) -> str:
    task_key = str(task or "").strip().lower()
    task_env_var = _TASK_ENV_VARS.get(task_key)

    if task_env_var:
        task_value = os.getenv(task_env_var, "").strip()
        if task_value:
            return task_value

    shared_value = os.getenv("GEMINI_MODEL", "").strip()
    if shared_value:
        return shared_value

    return _TASK_DEFAULTS.get(task_key, DEFAULT_GEMINI_MODEL)


def gemini_endpoint(task: str) -> str:
    model_name = resolve_gemini_model(task)
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
