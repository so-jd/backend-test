"""
Management command to export Open edX course structure to help create mapping files.

This command lists all courses and their modules/sequentials to help you
create the course_mapping.json file needed for the import_legacy_data command.

Usage:
    python manage.py export_course_structure

    python manage.py export_course_structure --course course-v1:Toyo+Tires+2024

    python manage.py export_course_structure --output structure.json
"""
import json
import logging

from django.core.management.base import BaseCommand
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Management command to export course structure for mapping purposes.
    """

    help = 'Export Open edX course structure to help create mapping files'

    def add_arguments(self, parser):
        """Define command arguments."""
        parser.add_argument(
            '--course',
            type=str,
            help='Specific course key to export (optional, exports all if not specified)'
        )
        parser.add_argument(
            '--output',
            type=str,
            help='Output JSON file path (optional, prints to stdout if not specified)'
        )
        parser.add_argument(
            '--include-units',
            action='store_true',
            help='Include individual units/verticals (default: only sequentials/modules)'
        )

    def _get_course_structure(self, course_key: CourseKey, include_units: bool = False):
        """Get the structure of a course."""
        try:
            from xmodule.modulestore.django import modulestore
        except ImportError:
            self.stdout.write(self.style.ERROR('Error: xmodule not available (not in LMS context)'))
            return None

        store = modulestore()
        course = store.get_course(course_key)

        if not course:
            return None

        structure = {
            'course_key': str(course_key),
            'display_name': course.display_name,
            'chapters': []
        }

        for chapter in course.get_children():
            chapter_data = {
                'display_name': chapter.display_name,
                'location': str(chapter.location),
                'sequentials': []
            }

            for sequential in chapter.get_children():
                sequential_data = {
                    'display_name': sequential.display_name,
                    'location': str(sequential.location)
                }

                if include_units:
                    sequential_data['units'] = []
                    for unit in sequential.get_children():
                        unit_data = {
                            'display_name': unit.display_name,
                            'location': str(unit.location)
                        }
                        sequential_data['units'].append(unit_data)

                chapter_data['sequentials'].append(sequential_data)

            structure['chapters'].append(chapter_data)

        return structure

    def handle(self, *args, **options):
        """Execute the command."""
        course_key_str = options.get('course')
        output_path = options.get('output')
        include_units = options.get('include_units', False)

        self.stdout.write(self.style.MIGRATE_HEADING('\n' + '=' * 80))
        self.stdout.write('EXPORTING COURSE STRUCTURE')
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80 + '\n'))

        # Get courses to export
        courses_to_export = []

        if course_key_str:
            # Specific course
            try:
                course_key = CourseKey.from_string(course_key_str)
                courses_to_export.append(course_key)
            except InvalidKeyError:
                self.stdout.write(self.style.ERROR(f'Invalid course key: {course_key_str}'))
                return
        else:
            # All courses
            try:
                from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
                courses_to_export = [c.id for c in CourseOverview.objects.all()]
                self.stdout.write(f'Found {len(courses_to_export)} courses\n')
            except ImportError:
                self.stdout.write(self.style.ERROR('Error: CourseOverview not available'))
                return

        # Export structures
        structures = []
        for course_key in courses_to_export:
            self.stdout.write(f'Exporting {course_key}...')
            structure = self._get_course_structure(course_key, include_units)
            if structure:
                structures.append(structure)
                self.stdout.write(self.style.SUCCESS(f'  ✓ Exported {course_key}'))
            else:
                self.stdout.write(self.style.WARNING(f'  ⚠ Could not export {course_key}'))

        # Output results
        output_data = {
            'courses': structures,
            'export_info': {
                'include_units': include_units,
                'course_count': len(structures)
            }
        }

        if output_path:
            # Write to file
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            self.stdout.write(
                self.style.SUCCESS(f'\n✓ Course structure exported to {output_path}')
            )
        else:
            # Print to stdout
            self.stdout.write('\n' + '=' * 80)
            self.stdout.write('COURSE STRUCTURE')
            self.stdout.write('=' * 80 + '\n')
            print(json.dumps(output_data, indent=2, ensure_ascii=False))

        self.stdout.write(self.style.MIGRATE_HEADING('\n' + '=' * 80))
        self.stdout.write(f'Exported {len(structures)} course(s)')
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80 + '\n'))
