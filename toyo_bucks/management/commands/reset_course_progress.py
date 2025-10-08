"""
Management command to reset a user's progress in a course.

This command deletes all progress-related data for a specific user in a specific course,
including:
- Block completions
- Student module state
- Grades (course and subsection)
- Toyo Bucks reward claims

WARNING: This operation is destructive and cannot be undone!
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey

log = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    """
    Management command to reset a user's course progress.

    Usage:
        python manage.py reset_course_progress <username> <course_key> --confirm
        python manage.py reset_course_progress <username> <course_key> --dry-run
    """

    help = (
        'Reset a user\'s progress in a course by deleting all completion and grade data. '
        'This is a destructive operation that requires --confirm flag.'
    )

    def add_arguments(self, parser):
        """Define command arguments."""
        parser.add_argument(
            'username',
            type=str,
            help='Username of the user whose progress should be reset'
        )
        parser.add_argument(
            'course_key',
            type=str,
            help='Course key (e.g., course-v1:OpenedX+Demo+2023)'
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm that you want to delete progress data (required for actual deletion)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview what would be deleted without actually deleting anything'
        )

    def handle(self, *args, **options):
        """Execute the command."""
        username = options['username']
        course_key_string = options['course_key']
        confirm = options['confirm']
        dry_run = options['dry_run']

        # Validate user exists
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'User not found: {username}')

        # Validate and parse course key
        try:
            course_key = CourseKey.from_string(course_key_string)
        except InvalidKeyError:
            raise CommandError(f'Invalid course key: {course_key_string}')

        # Check for confirmation
        if not dry_run and not confirm:
            raise CommandError(
                'This is a destructive operation. You must pass --confirm flag to proceed, '
                'or use --dry-run to preview changes.'
            )

        # Display header
        self.stdout.write(self.style.MIGRATE_HEADING('\n' + '=' * 70))
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No data will be deleted'))
        else:
            self.stdout.write(self.style.ERROR('RESETTING USER COURSE PROGRESS'))
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 70))
        self.stdout.write(f'User: {user.username} (ID: {user.id})')
        self.stdout.write(f'Course: {course_key}\n')

        # Collect deletion statistics
        stats = {}

        try:
            # Import models dynamically to avoid import errors if they don't exist
            models_to_check = [
                ('completion.models', 'BlockCompletion', 'user', 'context_key'),
                ('courseware.models', 'StudentModule', 'student', 'course_id'),
                ('lms.djangoapps.grades.models', 'PersistentCourseGrade', 'user_id', 'course_id'),
                ('lms.djangoapps.grades.models', 'PersistentSubsectionGrade', 'user_id', 'course_id'),
                ('toyo_bucks.models', 'RewardClaim', 'user', 'unit_key__course_key'),
            ]

            # Count and optionally delete records
            with transaction.atomic():
                for module_path, model_name, user_field, course_field in models_to_check:
                    try:
                        # Import the model
                        module = __import__(module_path, fromlist=[model_name])
                        model = getattr(module, model_name)

                        # Build query filter
                        if user_field == 'user':
                            filter_kwargs = {user_field: user}
                        else:
                            filter_kwargs = {user_field: user.id}

                        # Handle course field - some use direct course_key, others nested
                        if '__' in course_field:
                            # Nested lookup like unit_key__course_key
                            filter_kwargs[course_field] = course_key
                        else:
                            filter_kwargs[course_field] = course_key

                        # Query the records
                        queryset = model.objects.filter(**filter_kwargs)
                        count = queryset.count()
                        stats[model_name] = count

                        if count > 0:
                            self.stdout.write(
                                f'  {model_name}: {count} record(s) found'
                            )

                            # Delete if not dry run
                            if not dry_run:
                                deleted_count, _ = queryset.delete()
                                self.stdout.write(
                                    self.style.SUCCESS(f'    ✓ Deleted {deleted_count} record(s)')
                                )

                    except (ImportError, AttributeError) as e:
                        # Model doesn't exist in this installation, skip it
                        self.stdout.write(
                            self.style.WARNING(f'  {model_name}: Not available (skipped)')
                        )
                        log.debug(f'Model {model_name} not found: {e}')
                        continue
                    except Exception as e:
                        # Log but don't fail on individual model errors
                        self.stdout.write(
                            self.style.ERROR(f'  {model_name}: Error - {str(e)}')
                        )
                        log.exception(f'Error processing {model_name}')
                        continue

                # If dry run, rollback the transaction
                if dry_run:
                    transaction.set_rollback(True)

        except Exception as e:
            raise CommandError(f'Error resetting progress: {str(e)}')

        # Display summary
        self.stdout.write(self.style.MIGRATE_HEADING('\n' + '=' * 70))
        total_records = sum(stats.values())

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN COMPLETE - No changes made'))
            self.stdout.write(f'Would delete {total_records} total record(s)')
        else:
            self.stdout.write(self.style.SUCCESS('RESET COMPLETE'))
            self.stdout.write(f'Deleted {total_records} total record(s)')
            log.info(
                f'Reset course progress for user {username} in course {course_key}. '
                f'Deleted {total_records} records.'
            )

        self.stdout.write(self.style.MIGRATE_HEADING('=' * 70 + '\n'))

        # Display breakdown
        if stats:
            self.stdout.write('Breakdown by model:')
            for model_name, count in stats.items():
                if count > 0:
                    self.stdout.write(f'  • {model_name}: {count}')

        # Final warning if it was a real deletion
        if not dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'\n⚠️  User {username} will need to re-enroll or refresh '
                    f'to see the reset progress in course {course_key}'
                )
            )