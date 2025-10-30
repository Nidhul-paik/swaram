# Swaram/management/commands/ingest_data.py

import os
import csv
from django.core.management.base import BaseCommand
from django.core.files import File
from django.conf import settings
from Swaram.models import AudioFile


RAW_DATA_ROOT = 'raw_data'
FINAL_AUDIO_DIR = os.path.join('final_verified_data', 'audio_files')


class Command(BaseCommand):
    help = "Ingests audio metadata from raw_data folders into the Django database."

    def handle(self, *args, **options):
        if not os.path.exists(RAW_DATA_ROOT):
            self.stderr.write(self.style.ERROR(f"❌ Error: Root data directory '{RAW_DATA_ROOT}' not found."))
            return

        self.stdout.write(self.style.SUCCESS("🚀 Starting data ingestion with duration..."))

        total_added = 0
        total_skipped = 0

        for root, dirs, files in os.walk(RAW_DATA_ROOT):
            if 'metadata.csv' in files:
                metadata_path = os.path.join(root, 'metadata.csv')

                # Dynamically detect the source folder name
                path_parts = root.split(os.sep)
                source_folder = path_parts[1] if len(path_parts) > 1 else "unknown"

                audio_chunks_path = os.path.join(root, '05_final_chunks')
                self.stdout.write(f"\n📁 Processing folder: '{source_folder}'")

                with open(metadata_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        filename = row['filename']
                        local_audio_path = os.path.join(audio_chunks_path, filename)

                        if not os.path.exists(local_audio_path):
                            self.stdout.write(self.style.WARNING(f"  ⚠️ Missing file: {filename}"))
                            continue

                        try:
                            duration = int(row.get('duration_ms', 0))
                        except (ValueError, TypeError):
                            duration = 0
                            self.stdout.write(
                                self.style.WARNING(f"  ⚠️ Invalid duration for '{filename}'. Setting to 0.")
                            )

                        obj, created = AudioFile.objects.get_or_create(
                            source_folder=source_folder,
                            filename=filename,
                            defaults={
                                'original_transcription': row.get('transcription', ''),
                                'duration_ms': duration,
                            },
                        )

                        if created:
                            # Attach actual audio file if FileField exists
                            if hasattr(obj, "file"):
                                with open(local_audio_path, "rb") as audio_file:
                                    obj.file.save(filename, File(audio_file), save=True)
                            self.stdout.write(self.style.SUCCESS(f"  ✅ Added: {filename}"))
                            total_added += 1
                        else:
                            self.stdout.write(f"  ↩️ Skipped (already exists): {filename}")
                            total_skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✅ Data ingestion complete. Added: {total_added}, Skipped: {total_skipped}"
            )
        )
