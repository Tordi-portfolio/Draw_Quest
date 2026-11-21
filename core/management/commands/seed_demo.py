from decimal import Decimal

from django.core.management.base import BaseCommand

from core.models import Announcement, Task

DEMO_TASKS = [
    ("Neon city at midnight", "Draw a rain-soaked cyberpunk street with glowing signs and one lonely figure under an umbrella.", "digital", "12.00"),
    ("Your pet as a superhero", "Sketch your pet (or an imaginary one) in a hero costume. Cape optional, attitude required.", "character", "6.50"),
    ("A door to somewhere else", "Illustrate a single door standing alone in a landscape. What is behind it? Hint at it.", "sketch", "8.00"),
    ("Abstract: the sound of rain", "No objects. Use only shape, line and colour to express what rain sounds like.", "abstract", "5.00"),
    ("Mountain sunrise in 3 colours", "Paint or draw a mountain sunrise using only three colours.", "landscape", "7.25"),
    ("Redesign a village market", "Imagine a futuristic open-air market. Show stalls, people and one surprising detail.", "digital", "15.00"),
]


class Command(BaseCommand):
    help = "Creates a few demo tasks and a welcome announcement (only if none exist)."

    def handle(self, *args, **options):
        if Task.objects.exists():
            self.stdout.write("Tasks already exist. Nothing to do.")
            return
        for title, desc, cat, reward in DEMO_TASKS:
            Task.objects.create(
                title=title, description=desc, category=cat, reward=Decimal(reward)
            )
        Announcement.objects.create(
            title="Welcome to DrawQuest",
            body="New tasks drop every week. Draw, upload, get approved, get paid.",
        )
        self.stdout.write(self.style.SUCCESS(f"Created {len(DEMO_TASKS)} demo tasks."))
