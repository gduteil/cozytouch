"""Atlantic Cozytouch device model mapping."""


def get_model_name_from_id(modelId: int) -> str:
    """Return name from model ID."""
    if modelId == 56:
        return "Naema 2 Micro 25"
    elif modelId == 76:
        return "Alfea Extensa Duo AI UE"
    elif modelId == 235:
        return "Thermostat Navilink Connect"
    elif modelId == 556:
        return "Takao hub"
    elif modelId == 557:
        return "Takao M3 (557)"
    elif modelId == 558:
        return "Takao M3 (558)"
    elif modelId == 562:
        return "Takao M3 (557) UI"
    elif modelId == 563:
        return "Takao M3 (558) UI"
    elif modelId == 1353:
        return "Calypso Split Interface"
    elif modelId == 1376:
        return "Calypso Split 270L"

    return "Unknown product (" + str(modelId) + ")"
