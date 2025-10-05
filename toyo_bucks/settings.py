"""
Settings for Toyo Bucks Django application.
"""


def plugin_settings(settings):
    """
    Add Toyo Bucks specific settings to the LMS settings.

    Args:
        settings: The LMS Django settings module
    """
    # Default reward amount for units without specific configuration
    settings.TOYO_BUCKS_DEFAULT_REWARD = getattr(
        settings, "TOYO_BUCKS_DEFAULT_REWARD", 10.0
    )

    # Enable/disable auto-awarding on completion
    settings.TOYO_BUCKS_AUTO_AWARD_ENABLED = getattr(
        settings, "TOYO_BUCKS_AUTO_AWARD_ENABLED", True
    )

    # Maximum balance a user can have
    settings.TOYO_BUCKS_MAX_BALANCE = getattr(
        settings, "TOYO_BUCKS_MAX_BALANCE", 999999.99
    )

    # Minimum transaction amount
    settings.TOYO_BUCKS_MIN_TRANSACTION = getattr(
        settings, "TOYO_BUCKS_MIN_TRANSACTION", 0.01
    )
