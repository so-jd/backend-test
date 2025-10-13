"""
Management command to trigger asynchronous legacy data import.

This command submits the import job to a Celery worker, allowing you to
run the import without blocking the LMS server.

Usage:
    # Start async import
    python manage.py import_legacy_data_async \
        --learners /path/to/LearnersCourseActiveAndCompleted.csv \
        --courses /path/to/CoursesAndModules.csv \
        --mapping /path/to/course_mapping.json

    # Check status of running import
    python manage.py import_legacy_data_async --status <task_id>

    # List all import tasks
    python manage.py import_legacy_data_async --list
"""
import json
import logging
from django.core.management.base import BaseCommand, CommandError

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Management command to trigger asynchronous legacy data import.
    """

    help = (
        'Trigger asynchronous import of legacy enrollment and completion data. '
        'The import runs on a Celery worker to avoid blocking the LMS server.'
    )

    def add_arguments(self, parser):
        """Define command arguments."""
        parser.add_argument(
            '--learners',
            type=str,
            help='Path to LearnersCourseActiveAndCompleted.csv file'
        )
        parser.add_argument(
            '--courses',
            type=str,
            help='Path to CoursesAndModules.csv file'
        )
        parser.add_argument(
            '--mapping',
            type=str,
            help='Path to course_mapping.json file'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Number of records to process before updating progress (default: 1000)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit number of records to process (for testing)'
        )
        parser.add_argument(
            '--status',
            type=str,
            help='Check status of a running import task by task ID'
        )
        parser.add_argument(
            '--list',
            action='store_true',
            help='List recent import tasks and their status'
        )
        parser.add_argument(
            '--wait',
            action='store_true',
            help='Wait for the task to complete and show progress'
        )

    def _load_mapping(self, mapping_path: str) -> dict:
        """Load and validate the course mapping file."""
        try:
            with open(mapping_path, 'r', encoding='utf-8') as f:
                mapping = json.load(f)

            if 'courses' not in mapping:
                raise CommandError('Mapping file must contain "courses" key')

            return mapping
        except FileNotFoundError:
            raise CommandError(f'Mapping file not found: {mapping_path}')
        except json.JSONDecodeError as e:
            raise CommandError(f'Invalid JSON in mapping file: {e}')

    def _check_status(self, task_id: str):
        """Check the status of a task."""
        from celery.result import AsyncResult

        result = AsyncResult(task_id)

        self.stdout.write(self.style.MIGRATE_HEADING('\n' + '=' * 80))
        self.stdout.write(f'TASK STATUS: {task_id}')
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))

        self.stdout.write(f'\nState: {result.state}')

        if result.state == 'PENDING':
            self.stdout.write(self.style.WARNING('\nTask is pending or does not exist.'))
        elif result.state == 'PROGRESS':
            info = result.info
            if isinstance(info, dict):
                self.stdout.write(self.style.SUCCESS('\nTask is running:'))
                self._print_progress(info)
        elif result.state == 'SUCCESS':
            info = result.result
            self.stdout.write(self.style.SUCCESS('\nTask completed successfully!'))
            self._print_summary(info)
        elif result.state == 'FAILURE':
            self.stdout.write(self.style.ERROR(f'\nTask failed: {str(result.info)}'))
        else:
            self.stdout.write(f'\nInfo: {result.info}')

        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80 + '\n'))

    def _print_progress(self, info: dict):
        """Print task progress information."""
        processed = info.get('processed_records', 0)
        total = info.get('total_records', 0)
        percent = info.get('progress_percent', 0)

        self.stdout.write(f'  Progress: {processed:,} / {total:,} ({percent:.1f}%)')
        self.stdout.write(f'  Users created: {info.get("users_created", 0):,}')
        self.stdout.write(f'  Users existing: {info.get("users_existing", 0):,}')
        self.stdout.write(f'  Enrollments created: {info.get("enrollments_created", 0):,}')
        self.stdout.write(f'  Completions created: {info.get("completions_created", 0):,}')
        self.stdout.write(f'  Completions skipped: {info.get("completions_skipped", 0):,}')
        self.stdout.write(f'  ToyoBucks awarded: {info.get("toyo_bucks_awarded", "0.00")}')
        self.stdout.write(f'  Errors: {info.get("error_count", 0)}')
        self.stdout.write(f'  Skipped courses: {info.get("skipped_course_count", 0)}')

    def _print_summary(self, info: dict):
        """Print import summary."""
        self.stdout.write(f'\n  Total records: {info.get("processed_records", 0):,}')
        self.stdout.write(f'\n  Users:')
        self.stdout.write(f'    Created: {info.get("users_created", 0):,}')
        self.stdout.write(f'    Existing: {info.get("users_existing", 0):,}')
        self.stdout.write(f'\n  Enrollments:')
        self.stdout.write(f'    Created: {info.get("enrollments_created", 0):,}')
        self.stdout.write(f'    Existing: {info.get("enrollments_existing", 0):,}')
        self.stdout.write(f'\n  Completions:')
        self.stdout.write(f'    Created: {info.get("completions_created", 0):,}')
        self.stdout.write(f'    Skipped: {info.get("completions_skipped", 0):,}')
        self.stdout.write(f'\n  ToyoBucks awarded: {info.get("toyo_bucks_awarded", "0.00")}')

        errors = info.get('errors', [])
        if errors:
            self.stdout.write(f'\n  Errors ({len(errors)}):')
            for error in errors[:20]:
                self.stdout.write(f'    - {error}')
            if len(errors) > 20:
                self.stdout.write(f'    ... and {len(errors) - 20} more')

        skipped = info.get('skipped_courses', [])
        if skipped:
            self.stdout.write(f'\n  Skipped courses ({len(skipped)}):')
            for course in sorted(skipped)[:20]:
                self.stdout.write(f'    - {course}')
            if len(skipped) > 20:
                self.stdout.write(f'    ... and {len(skipped) - 20} more')

    def _list_tasks(self):
        """List recent import tasks."""
        from celery.result import AsyncResult
        from django.core.cache import cache

        # Get task IDs from cache (you might want to store these differently)
        task_ids = cache.get('legacy_import_tasks', [])

        if not task_ids:
            self.stdout.write(self.style.WARNING('\nNo recent import tasks found.'))
            self.stdout.write('\nNote: Task tracking requires tasks to be submitted via this command.')
            return

        self.stdout.write(self.style.MIGRATE_HEADING('\n' + '=' * 80))
        self.stdout.write('RECENT IMPORT TASKS')
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80 + '\n'))

        for task_id in task_ids[-10:]:  # Show last 10 tasks
            result = AsyncResult(task_id)
            status_style = {
                'SUCCESS': self.style.SUCCESS,
                'FAILURE': self.style.ERROR,
                'PROGRESS': self.style.WARNING,
                'PENDING': self.style.WARNING,
            }.get(result.state, lambda x: x)

            self.stdout.write(f'{task_id}: {status_style(result.state)}')

        self.stdout.write(self.style.MIGRATE_HEADING('\n' + '=' * 80))
        self.stdout.write('Use --status <task_id> to check details')
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80 + '\n'))

    def _wait_for_completion(self, task_id: str):
        """Wait for task to complete, showing progress."""
        from celery.result import AsyncResult
        import time

        result = AsyncResult(task_id)

        self.stdout.write('\nWaiting for task to complete...')
        self.stdout.write('Press Ctrl+C to stop waiting (task will continue running)\n')

        try:
            last_progress = 0
            while not result.ready():
                if result.state == 'PROGRESS':
                    info = result.info
                    if isinstance(info, dict):
                        current_progress = info.get('progress_percent', 0)
                        if current_progress != last_progress:
                            processed = info.get('processed_records', 0)
                            total = info.get('total_records', 0)
                            self.stdout.write(
                                f'\rProgress: {current_progress:.1f}% ({processed:,}/{total:,} records)',
                                ending=''
                            )
                            last_progress = current_progress

                time.sleep(2)  # Check every 2 seconds

            self.stdout.write('\n')

            # Task completed
            if result.successful():
                self.stdout.write(self.style.SUCCESS('\n✓ Import completed successfully!\n'))
                self._print_summary(result.result)
            else:
                self.stdout.write(self.style.ERROR(f'\n✗ Import failed: {result.info}\n'))

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING(
                f'\n\nStopped waiting. Task {task_id} is still running on worker.'
            ))
            self.stdout.write(f'Check status with: --status {task_id}\n')

    def handle(self, *args, **options):
        """Execute the command."""
        status_task_id = options.get('status')
        list_tasks = options.get('list')

        # Check status of existing task
        if status_task_id:
            self._check_status(status_task_id)
            return

        # List tasks
        if list_tasks:
            self._list_tasks()
            return

        # Start new import
        learners_path = options.get('learners')
        courses_path = options.get('courses')
        mapping_path = options.get('mapping')
        batch_size = options.get('batch_size', 1000)
        limit = options.get('limit')
        wait = options.get('wait', False)

        if not all([learners_path, courses_path, mapping_path]):
            raise CommandError(
                'Required arguments: --learners, --courses, --mapping\n'
                'Or use --status <task_id> to check task status\n'
                'Or use --list to list recent tasks'
            )

        # Display header
        self.stdout.write(self.style.MIGRATE_HEADING('\n' + '=' * 80))
        self.stdout.write('SUBMITTING ASYNC IMPORT TASK')
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))

        # Load mapping
        self.stdout.write('\nLoading course mapping...')
        mapping_data = self._load_mapping(mapping_path)
        self.stdout.write(self.style.SUCCESS(f'  ✓ Loaded {len(mapping_data["courses"])} course mappings'))

        # Import the task
        try:
            from toyo_bucks.tasks import import_legacy_data_async
        except ImportError:
            raise CommandError(
                'Could not import toyo_bucks.tasks. '
                'Make sure the toyo_bucks app is installed and Celery is configured.'
            )

        # Submit task
        self.stdout.write('\nSubmitting task to Celery worker...')

        result = import_legacy_data_async.delay(
            learners_path=learners_path,
            courses_path=courses_path,
            mapping_data=mapping_data,
            batch_size=batch_size,
            limit=limit
        )

        # Store task ID in cache for listing
        from django.core.cache import cache
        task_ids = cache.get('legacy_import_tasks', [])
        task_ids.append(result.id)
        cache.set('legacy_import_tasks', task_ids[-100:], timeout=86400 * 7)  # Keep for 7 days

        self.stdout.write(self.style.SUCCESS(f'\n✓ Task submitted successfully!'))
        self.stdout.write(f'\nTask ID: {result.id}')

        self.stdout.write(self.style.MIGRATE_HEADING('\n' + '=' * 80))
        self.stdout.write('NEXT STEPS')
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
        self.stdout.write(f'\n1. Check task status:')
        self.stdout.write(f'   python manage.py import_legacy_data_async --status {result.id}')
        self.stdout.write(f'\n2. Monitor Celery worker logs:')
        self.stdout.write(f'   tutor local logs -f celery-worker')
        self.stdout.write(f'\n3. Check all recent tasks:')
        self.stdout.write(f'   python manage.py import_legacy_data_async --list')
        self.stdout.write(self.style.MIGRATE_HEADING('\n' + '=' * 80 + '\n'))

        # Wait for completion if requested
        if wait:
            self._wait_for_completion(result.id)
