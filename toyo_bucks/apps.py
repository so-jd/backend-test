"""
Toyo Bucks Django application initialization.
"""

from django.apps import AppConfig
from edx_django_utils.plugins.constants import PluginSettings, PluginSignals, PluginURLs


class ToyoBucksConfig(AppConfig):
    """
    Configuration for the Toyo Bucks Django application.
    """

    name = "toyo_bucks"
    verbose_name = "Toyo Bucks"

    plugin_app = {
        # Configuration setting for Plugin URLs for this app.
        PluginURLs.CONFIG: {
            "lms.djangoapp": {
                # The namespace to provide to django's urls.include.
                PluginURLs.NAMESPACE: "toyo_bucks",
                # The application namespace to provide to django's urls.include.
                PluginURLs.APP_NAME: "toyo_bucks",
            }
        },
        PluginSettings.CONFIG: {
            "lms.djangoapp": {
                "common": {
                    PluginSettings.RELATIVE_PATH: "settings",
                }
            }
        },
        PluginSignals.CONFIG: {
            "lms.djangoapp": {
                PluginSignals.RELATIVE_PATH: "receivers",
                PluginSignals.RECEIVERS: [
                    {
                        PluginSignals.RECEIVER_FUNC_NAME: "award_bucks_on_completion",
                        PluginSignals.SIGNAL_PATH: "django.db.models.signals.post_save",
                        PluginSignals.SENDER_PATH: "completion.models.BlockCompletion",
                    }
                ],
            }
        },
    }
