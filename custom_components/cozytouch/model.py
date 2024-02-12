"""Atlantic Cozytouch device model mapping."""


def get_model_name_from_id(modelId: int) -> str:
    """Return name from model ID."""
    if modelId == 56:
        return "Naema 2 Micro 25"
    elif modelId == 235:
        return "Thermostat Navilink Connect"

    return "Unknown product (" + str(modelId) + ")"
