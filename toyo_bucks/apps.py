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
                # The regex to provide to django's urls.url.
                # Optional; Defaults to r''.
                # PluginURLs.REGEX: r"^api/toyo-bucks/",
                # The python path (relative to this app) to the URLs module to be plugged into the project.
                # Optional; Defaults to 'urls'.
                # PluginURLs.RELATIVE_PATH: "urls",
            }
        },
        PluginSettings.CONFIG: {
            "lms.djangoapp": {
                "common": {
                    PluginSettings.RELATIVE_PATH: "settings",
                }
            }
        },
        # Signal configuration removed - signals are connected manually in ready()
        # to avoid import errors during build phase when completion app may not be available
    }

    def ready(self):
        """
        Connect signal handlers when the app is ready.
        """
        # Import and connect signals manually to avoid build-time import errors
        try:
            from completion.signals import PROGRESS_COMPLETED
            from completion.models import BlockCompletion
            from .signals import award_bucks_on_completion

            PROGRESS_COMPLETED.connect(
                award_bucks_on_completion,
                sender=BlockCompletion,
                dispatch_uid='toyo_bucks_award_on_completion'
            )
        except ImportError:
            # completion app not available (e.g., during build or in CMS)
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                "Completion tracking not available. Toyo Bucks auto-reward will not work. "
                "Make sure the 'completion' app is installed in Open edX."
            )
