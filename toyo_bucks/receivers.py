"""Signal receivers for Toyo Bucks."""

import logging
from django.db import IntegrityError

from toyo_bucks.models import CourseUnitReward, RewardClaim

logger = logging.getLogger(__name__)


def award_bucks_on_completion(sender, instance, created, **kwargs):
    """
    Automatically award Toyo Bucks when a user completes a block.

    This signal handler is triggered when a BlockCompletion is saved.
    It checks if there's a reward configured for that unit and if the
    user hasn't already claimed it, then awards the Toyo Bucks.

    Args:
        sender: The BlockCompletion model class
        instance: The BlockCompletion instance being saved
        created: Boolean indicating if this is a new completion
        **kwargs: Additional signal parameters
    """
    # Only process when completion reaches 1.0 (fully complete)
    if instance.completion < 1.0:
        logger.debug(
            f"Block {instance.block_key} not fully complete "
            f"(completion={instance.completion}), skipping reward"
        )
        return

    user = instance.user
    block_key = instance.block_key

    logger.info(
        f"Completion detected for user {user.username} and block {block_key}"
    )

    # Check if there's a reward configured for this unit
    reward_amount = CourseUnitReward.get_reward_for_unit(block_key)

    if reward_amount is None:
        logger.debug(f"No reward configured for unit {block_key}")
        return

    # Check if user has already claimed this reward
    if RewardClaim.has_claimed(user, block_key):
        logger.debug(
            f"User {user.username} has already claimed reward for unit {block_key}"
        )
        return

    # Award the reward
    try:
        claim = RewardClaim.claim_reward(user, block_key, reward_amount)

        if claim:
            logger.info(
                f"Successfully awarded {reward_amount} Toyo Bucks to "
                f"{user.username} for completing unit {block_key}"
            )
        else:
            logger.warning(
                f"Could not award Toyo Bucks to {user.username} for unit "
                f"{block_key} - possibly already claimed in a race condition"
            )

    except IntegrityError as e:
        logger.warning(
            f"IntegrityError when awarding Toyo Bucks to {user.username} "
            f"for unit {block_key}: {e}"
        )
    except Exception as e:
        logger.exception(
            f"Error awarding Toyo Bucks to {user.username} for unit {block_key}: {e}"
        )
