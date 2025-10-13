"""
Celery tasks for Toyo Bucks application.

This module contains asynchronous tasks that can be executed by Celery workers,
reducing load on the LMS server.
"""
import csv
import html
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional, Tuple

from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey, UsageKey

log = logging.getLogger(__name__)
User = get_user_model()


class ImportProgress:
    """Track and report import progress."""

    def __init__(self, task_id):
        self.task_id = task_id
        self.users_created = 0
        self.users_existing = 0
        self.enrollments_created = 0
        self.enrollments_existing = 0
        self.completions_created = 0
        self.completions_skipped = 0
        self.toyo_bucks_awarded = Decimal('0.00')
        self.errors = []
        self.skipped_courses = set()
        self.processed_records = 0
        self.total_records = 0

    def to_dict(self):
        """Convert progress to dictionary for status updates."""
        return {
            'task_id': self.task_id,
            'processed_records': self.processed_records,
            'total_records': self.total_records,
            'progress_percent': (self.processed_records / self.total_records * 100) if self.total_records > 0 else 0,
            'users_created': self.users_created,
            'users_existing': self.users_existing,
            'enrollments_created': self.enrollments_created,
            'enrollments_existing': self.enrollments_existing,
            'completions_created': self.completions_created,
            'completions_skipped': self.completions_skipped,
            'toyo_bucks_awarded': str(self.toyo_bucks_awarded),
            'error_count': len(self.errors),
            'skipped_course_count': len(self.skipped_courses),
        }


def _decode_html_entities(text: str) -> str:
    """Decode HTML entities in text."""
    if not text:
        return text
    prev = None
    while prev != text:
        prev = text
        text = html.unescape(text)
    return text


def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse date string from CSV."""
    if not date_str or date_str.strip().upper() == 'NULL':
        return None

    date_str = date_str.strip()

    formats = [
        '%Y-%m-%d %H:%M:%S.%f',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.split('.')[0] + ('.' + date_str.split('.')[1][:6] if '.' in date_str else ''), fmt)
            return timezone.make_aware(dt, timezone.get_current_timezone())
        except (ValueError, IndexError):
            continue

    return None


def _get_or_create_user(email: str, first_name: str, last_name: str, progress: ImportProgress) -> Optional[User]:
    """Get or create a user by email."""
    email = email.strip().lower()

    try:
        user = User.objects.get(email=email)
        progress.users_existing += 1
        return user
    except User.DoesNotExist:
        username = email
        user = User.objects.create(
            username=username,
            email=email,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            is_active=True
        )
        progress.users_created += 1
        return user
    except Exception as e:
        log.exception(f'Error getting/creating user {email}: {e}')
        return None


def _enroll_user_in_course(user, course_key: CourseKey, mode: str, progress: ImportProgress) -> bool:
    """Enroll a user in a course."""
    try:
        from common.djangoapps.student.models import CourseEnrollment

        enrollment, created = CourseEnrollment.objects.get_or_create(
            user=user,
            course_id=course_key,
            defaults={'mode': mode}
        )

        if created:
            progress.enrollments_created += 1
        else:
            progress.enrollments_existing += 1

        return True
    except ImportError:
        log.warning('CourseEnrollment model not available')
        return False
    except Exception as e:
        log.exception(f'Error enrolling user {user.username} in {course_key}: {e}')
        return False


def _mark_completion(user, block_key: UsageKey, completion_date: datetime, progress: ImportProgress) -> bool:
    """Mark a block as completed for a user."""
    try:
        from completion.models import BlockCompletion

        completion, created = BlockCompletion.objects.get_or_create(
            user=user,
            context_key=block_key.course_key,
            block_key=block_key,
            defaults={
                'completion': 1.0,
                'created': completion_date,
                'modified': completion_date
            }
        )

        if created:
            progress.completions_created += 1
            return True
        else:
            if completion.completion < 1.0:
                completion.completion = 1.0
                completion.modified = completion_date
                completion.save()
            return False
    except ImportError:
        log.warning('BlockCompletion model not available')
        return False
    except Exception as e:
        log.exception(f'Error marking completion for {user.username} on {block_key}: {e}')
        return False


def _award_toyo_bucks(user, block_key: UsageKey, amount: Decimal, completion_date: datetime, progress: ImportProgress) -> bool:
    """Award Toyo Bucks for a completion."""
    if amount <= 0:
        return False

    try:
        from toyo_bucks.models import ToyoBucksAccount, ToyoBucksTransaction, RewardClaim

        account, _ = ToyoBucksAccount.objects.get_or_create(user=user)
        reference_id = f'legacy_import_{block_key}'

        if ToyoBucksTransaction.objects.filter(
            account=account,
            reference_id=reference_id
        ).exists():
            return False

        ToyoBucksTransaction.objects.create(
            account=account,
            amount=amount,
            transaction_type='reward',
            reference_id=reference_id,
            description=f'Legacy import: {block_key.block_id}',
            created=completion_date
        )

        account.balance += amount
        account.save()

        RewardClaim.objects.get_or_create(
            user=user,
            unit_key=block_key,
            defaults={
                'claimed_at': completion_date,
                'amount': amount
            }
        )

        progress.toyo_bucks_awarded += amount
        return True
    except Exception as e:
        log.exception(f'Error awarding Toyo Bucks to {user.username}: {e}')
        return False


@shared_task(bind=True, name='toyo_bucks.import_legacy_data')
def import_legacy_data_async(
    self,
    learners_path: str,
    courses_path: str,
    mapping_data: dict,
    batch_size: int = 1000,
    limit: Optional[int] = None
):
    """
    Asynchronous task to import legacy data.

    This task runs on a Celery worker, reducing load on the LMS server.

    Args:
        learners_path: Path to LearnersCourseActiveAndCompleted.csv
        courses_path: Path to CoursesAndModules.csv
        mapping_data: Course mapping configuration (parsed JSON)
        batch_size: Number of records to process before updating progress
        limit: Optional limit on number of records to process

    Returns:
        dict: Import statistics
    """
    progress = ImportProgress(self.request.id)

    try:
        # Load courses CSV
        log.info(f"Loading courses from {courses_path}")
        courses_map = {}

        with open(courses_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                course_name = row['CourseName'].strip()
                module_name = row['ModuleName'].strip()
                toyo_buck_str = row['ToyoBuckAmount'].strip()

                if toyo_buck_str and toyo_buck_str.upper() != 'NULL':
                    try:
                        toyo_bucks = Decimal(toyo_buck_str)
                    except:
                        toyo_bucks = Decimal('0.00')
                else:
                    toyo_bucks = Decimal('0.00')

                courses_map[(course_name, module_name)] = toyo_bucks

        # Get import settings
        import_settings = mapping_data.get('import_settings', {})
        default_mode = mapping_data.get('default_enrollment_mode', 'honor')

        # Count total records
        log.info(f"Counting records in {learners_path}")
        with open(learners_path, 'r', encoding='utf-8-sig') as f:
            progress.total_records = sum(1 for _ in f) - 1  # Subtract header

        log.info(f"Starting import of {progress.total_records} records")

        # Update task state
        self.update_state(
            state='PROGRESS',
            meta=progress.to_dict()
        )

        # Process learners CSV
        with open(learners_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)

            batch_records = []

            for row_num, row in enumerate(reader, start=2):
                if limit and progress.processed_records >= limit:
                    log.info(f"Reached limit of {limit} records")
                    break

                batch_records.append((row_num, row))

                # Process in batches
                if len(batch_records) >= batch_size:
                    _process_batch(
                        batch_records,
                        courses_map,
                        mapping_data,
                        import_settings,
                        default_mode,
                        progress
                    )

                    # Update task progress
                    self.update_state(
                        state='PROGRESS',
                        meta=progress.to_dict()
                    )

                    log.info(f"Processed {progress.processed_records}/{progress.total_records} records")
                    batch_records = []

            # Process remaining records
            if batch_records:
                _process_batch(
                    batch_records,
                    courses_map,
                    mapping_data,
                    import_settings,
                    default_mode,
                    progress
                )

        log.info(f"Import completed. Processed {progress.processed_records} records")

        # Return final statistics
        result = progress.to_dict()
        result['status'] = 'completed'
        result['errors'] = progress.errors[:100]  # Include first 100 errors
        result['skipped_courses'] = list(progress.skipped_courses)

        return result

    except Exception as e:
        log.exception(f"Error during import: {e}")
        self.update_state(
            state='FAILURE',
            meta={'error': str(e), 'progress': progress.to_dict()}
        )
        raise


def _process_batch(batch_records, courses_map, mapping_data, import_settings, default_mode, progress):
    """Process a batch of records within a transaction."""

    with transaction.atomic():
        for row_num, row in batch_records:
            try:
                progress.processed_records += 1

                # Extract data
                email = row['UserEmail'].strip()
                first_name = row['Name'].strip()
                last_name = row['Surname'].strip()
                course_name = _decode_html_entities(row['CourseName'].strip())
                module_name = _decode_html_entities(row['ModuleName'].strip())
                earned_bucks_str = row.get('EarnedToyoBucks', '0.00').strip()
                completion_date_str = row.get('ModuleCompletionDate', '').strip()

                # Skip test courses if configured
                if import_settings.get('skip_test_courses', True):
                    test_patterns = import_settings.get('test_course_patterns', [])
                    if any(pattern.lower() in course_name.lower() for pattern in test_patterns):
                        continue

                # Check if course is in mapping
                if course_name not in mapping_data['courses']:
                    progress.skipped_courses.add(course_name)
                    continue

                course_data = mapping_data['courses'][course_name]
                course_key_str = course_data['course_key']
                course_key = CourseKey.from_string(course_key_str)

                # Check if module is in mapping
                if module_name not in course_data.get('modules', {}):
                    progress.errors.append(f'Row {row_num}: Module not in mapping: {course_name} -> {module_name}')
                    continue

                module_key_str = course_data['modules'][module_name]
                module_key = UsageKey.from_string(module_key_str)

                # Get or create user
                user = _get_or_create_user(email, first_name, last_name, progress)
                if not user:
                    progress.errors.append(f'Row {row_num}: Failed to create user: {email}')
                    continue

                # Enroll user in course
                _enroll_user_in_course(user, course_key, default_mode, progress)

                # Parse completion date
                completion_date = _parse_date(completion_date_str)

                if completion_date:
                    # Mark completion
                    _mark_completion(user, module_key, completion_date, progress)

                    # Award Toyo Bucks
                    if import_settings.get('award_toyo_bucks_from_csv', True):
                        if earned_bucks_str and earned_bucks_str.upper() != 'NULL':
                            try:
                                amount = Decimal(earned_bucks_str)
                            except:
                                amount = courses_map.get((course_name, module_name), Decimal('0.00'))
                        else:
                            amount = courses_map.get((course_name, module_name), Decimal('0.00'))

                        _award_toyo_bucks(user, module_key, amount, completion_date, progress)
                else:
                    progress.completions_skipped += 1

            except Exception as e:
                progress.errors.append(f'Row {row_num}: {str(e)}')
                log.exception(f'Error processing row {row_num}: {e}')
                continue
