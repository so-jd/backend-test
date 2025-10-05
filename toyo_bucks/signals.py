"""
Django signal handlers for Toyo Bucks.

Handles automatic reward distribution when users complete course units.
"""

import logging

from django.db import IntegrityError
from django.dispatch import receiver

try:
    from completion.signals import PROGRESS_COMPLETED
    COMPLETION_AVAILABLE = True
except ImportError:
    COMPLETION_AVAILABLE = False
    PROGRESS_COMPLETED = None

from .models import CourseUnitReward, RewardClaim

log = logging.getLogger(__name__)


if COMPLETION_AVAILABLE:
    @receiver(PROGRESS_COMPLETED)
    def award_bucks_on_completion(sender, user, block_key, **kwargs):
        """
        Automatically award Toyo Bucks when a user completes a unit.

        This signal handler is triggered when a user completes a block (unit)
        in a course. It checks if there's a reward configured for that unit
        and if the user hasn't already claimed it, then awards the Toyo Bucks.

        Args:
            sender: The BlockCompletion model class
            user: The user who completed the unit
            block_key: The usage key of the completed block
            **kwargs: Additional signal parameters
        """
        log.info(
            f"Completion signal received for user {user.username} "
            f"and block {block_key}"
        )

        # Check if there's a reward configured for this unit
        reward_amount = CourseUnitReward.get_reward_for_unit(block_key)

        if reward_amount is None:
            log.debug(f"No reward configured for unit {block_key}")
            return

        # Check if user has already claimed this reward
        if RewardClaim.has_claimed(user, block_key):
            log.debug(
                f"User {user.username} has already claimed reward for unit {block_key}"
            )
            return

        # Award the reward
        try:
            claim = RewardClaim.claim_reward(user, block_key, reward_amount)

            if claim:
                log.info(
                    f"Successfully awarded {reward_amount} Toyo Bucks to "
                    f"{user.username} for completing unit {block_key}"
                )
            else:
                log.warning(
                    f"Could not award Toyo Bucks to {user.username} for unit "
                    f"{block_key} - possibly already claimed in a race condition"
                )

        except IntegrityError as e:
            log.warning(
                f"IntegrityError when awarding Toyo Bucks to {user.username} "
                f"for unit {block_key}: {e}"
            )
        except Exception as e:
            log.exception(
                f"Error awarding Toyo Bucks to {user.username} for unit {block_key}: {e}"
            )

else:
    log.warning(
        "Completion tracking not available. Toyo Bucks auto-reward will not work. "
        "Make sure the 'completion' app is installed in Open edX."
    )

    def award_bucks_on_completion(sender, user, block_key, **kwargs):
        """Dummy function when completion tracking is not available."""
        pass
