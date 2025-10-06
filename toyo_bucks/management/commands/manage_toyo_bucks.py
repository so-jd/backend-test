"""
Management command for Toyo Bucks rewards
"""
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from opaque_keys.edx.keys import CourseKey, UsageKey
from toyo_bucks.models import (
    ToyoBucksAccount,
    CourseUnitReward,
    RewardClaim,
    ToyoBucksTransaction,
)

User = get_user_model()


class Command(BaseCommand):
    help = 'Manage Toyo Bucks rewards and accounts'

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest='subcommand', help='Subcommands')

        # Add reward
        add_reward = subparsers.add_parser('add_reward', help='Add reward to a course unit')
        add_reward.add_argument('course_key', type=str, help='Course key (e.g., course-v1:OpenedX+Demo+2023)')
        add_reward.add_argument('unit_key', type=str, help='Unit key (block-v1:...)')
        add_reward.add_argument('amount', type=float, help='Reward amount')

        # List rewards
        list_rewards = subparsers.add_parser('list_rewards', help='List all rewards')
        list_rewards.add_argument('--course', type=str, help='Filter by course key')

        # Add rewards to all units in a course
        add_all = subparsers.add_parser('add_all_units', help='Add rewards to all units in a course')
        add_all.add_argument('course_key', type=str, help='Course key')
        add_all.add_argument('amount', type=float, help='Reward amount per unit')

        # View account
        view_account = subparsers.add_parser('view_account', help='View user account balance')
        view_account.add_argument('username', type=str, help='Username')

        # Manual credit
        credit = subparsers.add_parser('credit', help='Manually credit user account')
        credit.add_argument('username', type=str, help='Username')
        credit.add_argument('amount', type=float, help='Amount to credit')
        credit.add_argument('--description', type=str, default='Manual credit', help='Transaction description')

    def handle(self, *args, **options):
        subcommand = options.get('subcommand')

        if not subcommand:
            self.print_help('manage.py', 'manage_toyo_bucks')
            return

        if subcommand == 'add_reward':
            self.add_reward(options)
        elif subcommand == 'list_rewards':
            self.list_rewards(options)
        elif subcommand == 'add_all_units':
            self.add_all_units(options)
        elif subcommand == 'view_account':
            self.view_account(options)
        elif subcommand == 'credit':
            self.credit_account(options)

    def add_reward(self, options):
        """Add reward to a specific unit"""
        try:
            course_key = CourseKey.from_string(options['course_key'])
            unit_key = UsageKey.from_string(options['unit_key'])
            amount = Decimal(str(options['amount']))

            reward, created = CourseUnitReward.objects.update_or_create(
                unit_key=unit_key,
                defaults={
                    'course_key': course_key,
                    'reward_amount': amount,
                }
            )

            if created:
                self.stdout.write(self.style.SUCCESS(
                    f'✓ Created reward: {amount} TB for {unit_key}'
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f'✓ Updated reward: {amount} TB for {unit_key}'
                ))

        except Exception as e:
            raise CommandError(f'Error adding reward: {e}')

    def list_rewards(self, options):
        """List all rewards"""
        course_filter = options.get('course')

        rewards = CourseUnitReward.objects.all()
        if course_filter:
            try:
                course_key = CourseKey.from_string(course_filter)
                rewards = rewards.filter(course_key=course_key)
            except Exception as e:
                raise CommandError(f'Invalid course key: {e}')

        if not rewards.exists():
            self.stdout.write(self.style.WARNING('No rewards found'))
            return

        self.stdout.write(self.style.SUCCESS(f'\nFound {rewards.count()} rewards:\n'))

        current_course = None
        total_by_course = {}

        for reward in rewards.order_by('course_key', 'created'):
            course_str = str(reward.course_key)
            if course_str != current_course:
                if current_course:
                    self.stdout.write(f'  Total: {total_by_course[current_course]} TB\n')
                current_course = course_str
                total_by_course[current_course] = Decimal('0')
                self.stdout.write(self.style.MIGRATE_HEADING(f'\n{current_course}'))

            total_by_course[current_course] += reward.reward_amount
            self.stdout.write(f'  • {reward.reward_amount} TB - {reward.unit_key}')

        if current_course:
            self.stdout.write(f'  Total: {total_by_course[current_course]} TB\n')

    def add_all_units(self, options):
        """Add rewards to all units in a course"""
        try:
            from xmodule.modulestore.django import modulestore

            course_key = CourseKey.from_string(options['course_key'])
            amount = Decimal(str(options['amount']))

            course = modulestore().get_course(course_key)
            if not course:
                raise CommandError(f'Course not found: {course_key}')

            units = []
            for chapter in course.get_children():
                for sequential in chapter.get_children():
                    for vertical in sequential.get_children():
                        units.append(vertical.location)

            if not units:
                raise CommandError('No units found in course')

            self.stdout.write(f'Found {len(units)} units. Adding {amount} TB to each...\n')

            created_count = 0
            updated_count = 0

            for unit_key in units:
                reward, created = CourseUnitReward.objects.update_or_create(
                    unit_key=unit_key,
                    defaults={
                        'course_key': course_key,
                        'reward_amount': amount,
                    }
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1

            total = amount * len(units)
            self.stdout.write(self.style.SUCCESS(
                f'\n✓ Done! Created: {created_count}, Updated: {updated_count}'
            ))
            self.stdout.write(self.style.SUCCESS(
                f'✓ Total available: {total} TB across {len(units)} units'
            ))

        except Exception as e:
            raise CommandError(f'Error: {e}')

    def view_account(self, options):
        """View user account"""
        try:
            user = User.objects.get(username=options['username'])
            account, created = ToyoBucksAccount.objects.get_or_create(user=user)

            self.stdout.write(self.style.MIGRATE_HEADING(f'\nAccount: {user.username}'))
            self.stdout.write(f'Balance: {account.balance} TB')
            self.stdout.write(f'Total Earned: {account.total_earned} TB')
            self.stdout.write(f'Total Spent: {account.total_spent} TB')

            # Recent transactions
            recent = ToyoBucksTransaction.objects.filter(account=account).order_by('-created')[:5]
            if recent:
                self.stdout.write(self.style.MIGRATE_HEADING('\nRecent Transactions:'))
                for txn in recent:
                    sign = '+' if txn.transaction_type != 'deduction' else '-'
                    self.stdout.write(
                        f'  {sign}{txn.amount} TB - {txn.transaction_type} - {txn.description}'
                    )

        except User.DoesNotExist:
            raise CommandError(f'User not found: {options["username"]}')

    def credit_account(self, options):
        """Manually credit account"""
        try:
            user = User.objects.get(username=options['username'])
            account, created = ToyoBucksAccount.objects.get_or_create(user=user)

            amount = Decimal(str(options['amount']))
            description = options['description']

            old_balance = account.balance
            account.add_balance(
                amount=amount,
                transaction_type='manual_adjustment',
                description=description,
            )

            self.stdout.write(self.style.SUCCESS(
                f'✓ Credited {amount} TB to {user.username}'
            ))
            self.stdout.write(f'  Old balance: {old_balance} TB')
            self.stdout.write(f'  New balance: {account.balance} TB')

        except User.DoesNotExist:
            raise CommandError(f'User not found: {options["username"]}')
        except Exception as e:
            raise CommandError(f'Error: {e}')
