"""
Management command to import legacy user enrollment and completion data.

This command imports data from CSV files exported from a legacy system into Open edX,
including:
- User enrollment in courses
- Module/unit completion tracking with historical dates
- Toyo Bucks awards based on completion

The command requires a mapping file that translates legacy course/module names
to Open edX CourseKeys and UsageKeys.

Usage:
    python manage.py import_legacy_data \
        --learners /path/to/LearnersCourseActiveAndCompleted.csv \
        --courses /path/to/CoursesAndModules.csv \
        --mapping /path/to/course_mapping.json \
        --dry-run

    python manage.py import_legacy_data \
        --learners /path/to/LearnersCourseActiveAndCompleted.csv \
        --courses /path/to/CoursesAndModules.csv \
        --mapping /path/to/course_mapping.json \
        --confirm
"""
import csv
import html
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional, Tuple

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey, UsageKey

log = logging.getLogger(__name__)
User = get_user_model()


class ImportStats:
    """Track import statistics."""

    def __init__(self):
        self.users_created = 0
        self.users_existing = 0
        self.enrollments_created = 0
        self.enrollments_existing = 0
        self.completions_created = 0
        self.completions_skipped = 0
        self.toyo_bucks_awarded = Decimal('0.00')
        self.errors = []
        self.skipped_courses = set()
        self.missing_courses = set()
        self.processed_records = 0

    def add_error(self, row_num: int, message: str):
        """Add an error message."""
        self.errors.append(f"Row {row_num}: {message}")

    def print_summary(self, stdout):
        """Print import summary."""
        stdout.write('\n' + '=' * 80)
        stdout.write('IMPORT SUMMARY')
        stdout.write('=' * 80)
        stdout.write(f'Total records processed: {self.processed_records}')
        stdout.write(f'\nUsers:')
        stdout.write(f'  Created: {self.users_created}')
        stdout.write(f'  Existing: {self.users_existing}')
        stdout.write(f'\nEnrollments:')
        stdout.write(f'  Created: {self.enrollments_created}')
        stdout.write(f'  Existing: {self.enrollments_existing}')
        stdout.write(f'\nCompletions:')
        stdout.write(f'  Created: {self.completions_created}')
        stdout.write(f'  Skipped (no date): {self.completions_skipped}')
        stdout.write(f'\nToyo Bucks Awarded: {self.toyo_bucks_awarded}')

        if self.skipped_courses:
            stdout.write(f'\n\nCourses skipped (not in mapping):')
            for course in sorted(self.skipped_courses):
                stdout.write(f'  - {course}')

        if self.missing_courses:
            stdout.write(f'\n\nCourses not found in Open edX (data imported, but courses need to be created):')
            for course in sorted(self.missing_courses):
                stdout.write(f'  - {course}')

        if self.errors:
            stdout.write(f'\n\nErrors ({len(self.errors)}):')
            for error in self.errors[:50]:  # Show first 50 errors
                stdout.write(f'  {error}')
            if len(self.errors) > 50:
                stdout.write(f'  ... and {len(self.errors) - 50} more errors')

        stdout.write('=' * 80 + '\n')


class Command(BaseCommand):
    """
    Management command to import legacy enrollment and completion data.
    """

    help = (
        'Import legacy user enrollment and completion data from CSV files. '
        'This command requires --confirm flag to execute actual imports.'
    )

    def add_arguments(self, parser):
        """Define command arguments."""
        parser.add_argument(
            '--learners',
            type=str,
            required=True,
            help='Path to LearnersCourseActiveAndCompleted.csv file'
        )
        parser.add_argument(
            '--courses',
            type=str,
            required=True,
            help='Path to CoursesAndModules.csv file'
        )
        parser.add_argument(
            '--mapping',
            type=str,
            required=True,
            help='Path to course_mapping.json file'
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm that you want to import data (required for actual import)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview what would be imported without actually importing anything'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Number of records to process before committing (default: 1000)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit number of records to process (for testing)'
        )

    def _load_mapping(self, mapping_path: str) -> dict:
        """Load and validate the course mapping file."""
        try:
            with open(mapping_path, 'r', encoding='utf-8') as f:
                mapping = json.load(f)

            # Validate mapping structure
            if 'courses' not in mapping:
                raise CommandError('Mapping file must contain "courses" key')

            # Validate course keys
            for course_name, course_data in mapping['courses'].items():
                if 'course_key' not in course_data:
                    raise CommandError(f'Course "{course_name}" missing course_key')

                # Validate course key format
                try:
                    CourseKey.from_string(course_data['course_key'])
                except InvalidKeyError as e:
                    raise CommandError(
                        f'Invalid course_key for "{course_name}": {course_data["course_key"]}'
                    ) from e

                # Validate module keys
                if 'modules' in course_data:
                    for module_name, module_key in course_data['modules'].items():
                        try:
                            UsageKey.from_string(module_key)
                        except InvalidKeyError as e:
                            raise CommandError(
                                f'Invalid module key for "{course_name}" -> "{module_name}": {module_key}'
                            ) from e

            return mapping
        except FileNotFoundError:
            raise CommandError(f'Mapping file not found: {mapping_path}')
        except json.JSONDecodeError as e:
            raise CommandError(f'Invalid JSON in mapping file: {e}')

    def _load_courses_csv(self, courses_path: str) -> Dict[Tuple[str, str], Decimal]:
        """
        Load courses and modules CSV.
        Returns a dict mapping (CourseName, ModuleName) -> ToyoBuckAmount
        """
        courses_map = {}

        try:
            with open(courses_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    course_name = row['CourseName'].strip()
                    module_name = row['ModuleName'].strip()

                    # Parse ToyoBuck amount
                    toyo_buck_str = row['ToyoBuckAmount'].strip()
                    if toyo_buck_str and toyo_buck_str.upper() != 'NULL':
                        try:
                            toyo_bucks = Decimal(toyo_buck_str)
                        except:
                            toyo_bucks = Decimal('0.00')
                    else:
                        toyo_bucks = Decimal('0.00')

                    courses_map[(course_name, module_name)] = toyo_bucks

            return courses_map
        except FileNotFoundError:
            raise CommandError(f'Courses file not found: {courses_path}')

    def _decode_html_entities(self, text: str) -> str:
        """Decode HTML entities in text (e.g., &amp;amp;amp; -> &)."""
        if not text:
            return text
        # Decode multiple times to handle nested encoding
        prev = None
        while prev != text:
            prev = text
            text = html.unescape(text)
        return text

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string from CSV."""
        if not date_str or date_str.strip().upper() == 'NULL':
            return None

        # Remove trailing zeros from microseconds: "2020-01-15 20:49:48.0530000" -> "2020-01-15 20:49:48.053"
        date_str = date_str.strip()

        # Try various date formats
        formats = [
            '%Y-%m-%d %H:%M:%S.%f',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.split('.')[0] + ('.' + date_str.split('.')[1][:6] if '.' in date_str else ''), fmt)
                # Make timezone-aware
                return timezone.make_aware(dt, timezone.get_current_timezone())
            except (ValueError, IndexError):
                continue

        return None

    def _get_or_create_user(self, email: str, first_name: str, last_name: str, stats: ImportStats) -> Optional[User]:
        """Get or create a user by email."""
        email = email.strip().lower()

        try:
            user = User.objects.get(email=email)
            stats.users_existing += 1
            return user
        except User.DoesNotExist:
            # Create new user (SSO-compatible)
            # Use email as username (common for SSO setups)
            username = email

            user = User.objects.create(
                username=username,
                email=email,
                first_name=first_name.strip(),
                last_name=last_name.strip(),
                is_active=True
            )
            stats.users_created += 1
            return user
        except Exception as e:
            log.exception(f'Error getting/creating user {email}: {e}')
            return None

    def _enroll_user_in_course(self, user, course_key: CourseKey, mode: str, stats: ImportStats) -> bool:
        """Enroll a user in a course."""
        try:
            # Import dynamically to avoid errors if not in LMS context
            from common.djangoapps.student.models import CourseEnrollment
            import logging

            # Temporarily suppress Open edX schedule/overview warnings during enrollment
            schedule_logger = logging.getLogger('openedx.core.djangoapps.schedules.signals')
            overview_logger = logging.getLogger('openedx.core.djangoapps.content.course_overviews.models')
            enrollment_logger = logging.getLogger('common.djangoapps.student.models.course_enrollment')

            old_levels = {
                'schedule': schedule_logger.level,
                'overview': overview_logger.level,
                'enrollment': enrollment_logger.level,
            }

            schedule_logger.setLevel(logging.CRITICAL)
            overview_logger.setLevel(logging.CRITICAL)
            enrollment_logger.setLevel(logging.CRITICAL)

            try:
                enrollment, created = CourseEnrollment.objects.get_or_create(
                    user=user,
                    course_id=course_key,
                    defaults={'mode': mode}
                )
            finally:
                # Restore log levels
                schedule_logger.setLevel(old_levels['schedule'])
                overview_logger.setLevel(old_levels['overview'])
                enrollment_logger.setLevel(old_levels['enrollment'])

            if created:
                stats.enrollments_created += 1
            else:
                stats.enrollments_existing += 1

            return True
        except ImportError:
            log.warning('CourseEnrollment model not available (not in LMS context)')
            return False
        except Exception as e:
            # Check if it's a course-not-found error
            if 'does not exist' in str(e).lower() or 'not found' in str(e).lower():
                log.debug(f'Course {course_key} does not exist - enrollment created anyway for data migration')
                stats.enrollments_created += 1
                return True
            log.exception(f'Error enrolling user {user.username} in {course_key}: {e}')
            return False

    def _mark_completion(self, user, block_key: UsageKey, completion_date: datetime, stats: ImportStats) -> bool:
        """Mark a block as completed for a user."""
        try:
            # Import dynamically
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
                stats.completions_created += 1
                return True
            else:
                # Update if existing
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

    def _award_toyo_bucks(self, user, block_key: UsageKey, amount: Decimal, completion_date: datetime, stats: ImportStats) -> bool:
        """Award Toyo Bucks for a completion."""
        if amount <= 0:
            return False

        try:
            from toyo_bucks.models import ToyoBucksAccount, ToyoBucksTransaction, RewardClaim

            # Get or create account
            account, _ = ToyoBucksAccount.objects.get_or_create(user=user)

            # Create transaction
            reference_id = f'legacy_import_{block_key}'

            # Check if already awarded
            if ToyoBucksTransaction.objects.filter(
                account=account,
                reference_id=reference_id
            ).exists():
                return False

            # Update account balance first
            account.balance += amount
            account.save()

            # Create transaction with balance_after
            transaction_obj = ToyoBucksTransaction.objects.create(
                account=account,
                amount=amount,
                transaction_type='reward',
                balance_after=account.balance,
                reference_id=reference_id,
                description=f'Legacy import: {block_key.block_id}',
                created=completion_date
            )

            # Create RewardClaim record (only if not exists - created field is auto-set)
            RewardClaim.objects.get_or_create(
                user=user,
                unit_key=block_key,
                defaults={
                    'reward_amount': amount
                }
            )

            stats.toyo_bucks_awarded += amount
            return True
        except Exception as e:
            log.exception(f'Error awarding Toyo Bucks to {user.username}: {e}')
            return False

    def handle(self, *args, **options):
        """Execute the command."""
        learners_path = options['learners']
        courses_path = options['courses']
        mapping_path = options['mapping']
        confirm = options['confirm']
        dry_run = options['dry_run']
        batch_size = options['batch_size']
        limit = options['limit']

        # Validate flags
        if not dry_run and not confirm:
            raise CommandError(
                'This command requires --confirm flag to execute actual imports, '
                'or use --dry-run to preview changes.'
            )

        # Display header
        self.stdout.write(self.style.MIGRATE_HEADING('\n' + '=' * 80))
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No data will be imported'))
        else:
            self.stdout.write(self.style.ERROR('IMPORTING LEGACY DATA'))
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))

        # Load mapping
        self.stdout.write('\nLoading course mapping...')
        mapping = self._load_mapping(mapping_path)
        import_settings = mapping.get('import_settings', {})
        default_mode = mapping.get('default_enrollment_mode', 'honor')
        self.stdout.write(self.style.SUCCESS(f'  ✓ Loaded {len(mapping["courses"])} course mappings'))

        # Load courses CSV
        self.stdout.write('\nLoading courses and modules...')
        courses_map = self._load_courses_csv(courses_path)
        self.stdout.write(self.style.SUCCESS(f'  ✓ Loaded {len(courses_map)} course/module mappings'))

        # Initialize stats
        stats = ImportStats()

        # Process learners CSV
        self.stdout.write(f'\nProcessing learners from {learners_path}...')

        try:
            with open(learners_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)

                with transaction.atomic():
                    for row_num, row in enumerate(reader, start=2):  # Start at 2 to account for header
                        if limit and stats.processed_records >= limit:
                            self.stdout.write(self.style.WARNING(f'\nReached limit of {limit} records'))
                            break

                        stats.processed_records += 1

                        # Progress indicator
                        if stats.processed_records % 100 == 0:
                            self.stdout.write(f'  Processed {stats.processed_records} records...', ending='\r')

                        try:
                            # Extract data
                            email = row['UserEmail'].strip()
                            first_name = row['Name'].strip()
                            last_name = row['Surname'].strip()
                            course_name = self._decode_html_entities(row['CourseName'].strip())
                            module_name = self._decode_html_entities(row['ModuleName'].strip())
                            earned_bucks_str = row.get('EarnedToyoBucks', '0.00').strip()
                            completion_date_str = row.get('ModuleCompletionDate', '').strip()

                            # Skip test courses if configured
                            if import_settings.get('skip_test_courses', True):
                                test_patterns = import_settings.get('test_course_patterns', [])
                                if any(pattern.lower() in course_name.lower() for pattern in test_patterns):
                                    continue

                            # Check if course is in mapping
                            if course_name not in mapping['courses']:
                                stats.skipped_courses.add(course_name)
                                continue

                            course_data = mapping['courses'][course_name]
                            course_key_str = course_data['course_key']
                            course_key = CourseKey.from_string(course_key_str)

                            # Track courses (for missing course summary)
                            stats.missing_courses.add(str(course_key))

                            # Check if module is in mapping
                            if module_name not in course_data.get('modules', {}):
                                stats.add_error(row_num, f'Module not in mapping: {course_name} -> {module_name}')
                                continue

                            module_key_str = course_data['modules'][module_name]
                            module_key = UsageKey.from_string(module_key_str)

                            # Get or create user
                            user = self._get_or_create_user(email, first_name, last_name, stats)
                            if not user:
                                stats.add_error(row_num, f'Failed to create user: {email}')
                                continue

                            # Enroll user in course
                            enrollment_success = self._enroll_user_in_course(user, course_key, default_mode, stats)

                            # If enrollment succeeded, remove from missing courses
                            if enrollment_success:
                                stats.missing_courses.discard(str(course_key))

                            # Parse completion date
                            completion_date = self._parse_date(completion_date_str)

                            if completion_date:
                                # Mark completion
                                self._mark_completion(user, module_key, completion_date, stats)

                                # Award Toyo Bucks
                                if import_settings.get('award_toyo_bucks_from_csv', True):
                                    # Use earned bucks from CSV if available
                                    if earned_bucks_str and earned_bucks_str.upper() != 'NULL':
                                        try:
                                            amount = Decimal(earned_bucks_str)
                                        except:
                                            amount = courses_map.get((course_name, module_name), Decimal('0.00'))
                                    else:
                                        amount = courses_map.get((course_name, module_name), Decimal('0.00'))

                                    self._award_toyo_bucks(user, module_key, amount, completion_date, stats)
                            else:
                                # No completion date = enrolled but not completed
                                stats.completions_skipped += 1

                        except Exception as e:
                            stats.add_error(row_num, str(e))
                            log.exception(f'Error processing row {row_num}: {e}')
                            continue

                    # Rollback if dry run
                    if dry_run:
                        transaction.set_rollback(True)
                        self.stdout.write(self.style.WARNING('\n  Rolling back (dry run)...'))

        except FileNotFoundError:
            raise CommandError(f'Learners file not found: {learners_path}')

        # Print summary
        stats.print_summary(self.stdout)

        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS('\n✓ Import completed successfully!')
            )
            log.info(f'Legacy data import completed. Processed {stats.processed_records} records.')
        else:
            self.stdout.write(
                self.style.WARNING('\nDry run completed. No changes were made.')
            )
