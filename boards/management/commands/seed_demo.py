import datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from boards.models import Board, Card

DEMO_PASSWORD = "demo-password-12345"

PEOPLE = [
    ("asha", "Asha", "Rao"),
    ("kabir", "Kabir", "Menon"),
    ("lena", "Lena", "Fischer"),
]

BOARDS = {
    "Website Redesign": [
        ("Audit the current pages", "todo", 2, None),
        ("Wireframe the new homepage", "todo", 3, 7),
        ("Pick a typeface", "todo", 1, None),
        ("Write the copy deck", "in_progress", 2, 3),
        ("Build the component library", "in_progress", 3, 14),
        ("Ship the staging build", "done", 2, None),
    ],
    "Internal Tools": [
        ("Replace the spreadsheet", "todo", 3, 10),
        ("Document the deploy steps", "todo", 1, None),
        ("Move CI to the new runner", "in_progress", 2, 5),
        ("Retire the old dashboard", "done", 1, None),
    ],
}


class Command(BaseCommand):
    help = "Create demo boards, people and cards for developing the UI against."

    def handle(self, *args, **options):
        User = get_user_model()
        today = datetime.date.today()

        people = []
        for username, first_name, last_name in PEOPLE:
            person, created = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first_name, "last_name": last_name},
            )
            if created:
                person.set_password(DEMO_PASSWORD)
                person.save()
            people.append(person)

        for index, (board_name, cards) in enumerate(BOARDS.items()):
            board, created = Board.objects.get_or_create(
                name=board_name,
                defaults={
                    "description": f"Demo board: {board_name}",
                    "created_by": people[0],
                },
            )
            if not created:
                continue

            counters = {"todo": 0, "in_progress": 0, "done": 0}
            for card_index, (title, status, priority, due_in_days) in enumerate(cards):
                Card.objects.create(
                    board=board,
                    title=title,
                    description=f"Seeded card for {board_name}.",
                    status=status,
                    priority=priority,
                    due_date=None if due_in_days is None
                    else today + datetime.timedelta(days=due_in_days),
                    assignee=people[card_index % len(people)],
                    position=counters[status],
                    created_by=people[index % len(people)],
                )
                counters[status] += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {Board.objects.count()} boards, "
                f"{Card.objects.count()} cards. "
                f"Demo logins use the password: {DEMO_PASSWORD}"
            )
        )
