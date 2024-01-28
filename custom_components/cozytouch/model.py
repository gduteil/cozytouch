"""Atlantic Cozytouch device model mapping."""


def get_model_name_from_id(modelId: int) -> str:
    """Return name from model ID."""
    if modelId == 235:
        return "Navilink 128 Radio-Connect"

    return "Unknown product (" + str(modelId) + ")"
