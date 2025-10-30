# Swaram/management/commands/ingest_images.py

import os
from django.core.management.base import BaseCommand
from Swaram.models import ImageContribution  # Make sure model name matches

class Command(BaseCommand):
    help = "Ingest images into the ImageContribution table from the contribution_assets/images directory"

    def handle(self, *args, **options):
        IMAGE_DIR = os.path.join('contribution_assets', 'images')

        if not os.path.isdir(IMAGE_DIR):
            self.stdout.write(self.style.ERROR(f"Error: Image directory not found at '{IMAGE_DIR}'. Please create it."))
            return

        self.stdout.write("Ingesting images into database...")

        image_files = [
            f for f in os.listdir(IMAGE_DIR)
            if os.path.isfile(os.path.join(IMAGE_DIR, f))
        ]

        added_count = 0

        for filename in image_files:
            if not ImageContribution.objects.filter(image_filename=filename).exists():
                ImageContribution.objects.create(image_filename=filename)
                self.stdout.write(self.style.SUCCESS(f"  - Added '{filename}'"))
                added_count += 1

        self.stdout.write(self.style.SUCCESS(f"\n✅ Image ingestion complete. {added_count} new images added."))
