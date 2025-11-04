import json
from Swaram.models import User, AudioFile, ImageContribution
from django.db import transaction

with open("sqlite_data.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print("🚀 Starting import...")

# --- USERS ---
user_cache = {}
for u in data.get("users", []):
    user, _ = User.objects.get_or_create(
        username=u["username"],
        defaults={
            "password": u["password"],  # hashed
            "full_name": u.get("full_name", ""),
            "role": u.get("role", ""),
            "api_token": u.get("api_token"),
        },
    )
    user_cache[u["id"]] = user.id  # map old ID → new ID

print(f"✅ Imported/linked {len(user_cache)} users")

# --- AUDIO FILES ---
audio_data = data.get("audio_files", [])
audio_fields = [f.name for f in AudioFile._meta.get_fields()]

use_fk = "verified_by" in audio_fields  # Detect if model uses FK fields

with transaction.atomic():
    for a in audio_data:
        # Map old SQLite user IDs to new ones
        assigned_id = user_cache.get(a.get("assigned_to")) if a.get("assigned_to") else None
        verified_id = user_cache.get(a.get("verified_by")) if a.get("verified_by") else None

        # Prepare defaults
        defaults = {
            "original_transcription": a.get("original_transcription", ""),
            "corrected_transcription": a.get("corrected_transcription", ""),
            "status": a.get("status", "pending"),
            "duration_ms": a.get("duration_ms"),
            "verified_at": a.get("verified_at"),
            "file": a.get("file", ""),
        }

        if use_fk:
            defaults["assigned_to_id"] = assigned_id
            defaults["verified_by_id"] = verified_id
        else:
            defaults["assigned_to_id"] = assigned_id
            defaults["verified_by_id"] = verified_id

        AudioFile.objects.update_or_create(
            source_folder=a["source_folder"],
            filename=a["filename"],
            defaults=defaults,
        )

print("🎧 Imported all audio files successfully!")

# --- IMAGE CONTRIBUTIONS ---
for ic in data.get("image_contributions", []):
    ImageContribution.objects.update_or_create(
        image_filename=ic["image_filename"],
        defaults={
            "audio_filename": ic.get("audio_filename"),
            "status": ic.get("status", "pending"),
            "assigned_to_id": user_cache.get(ic.get("assigned_to")),
            "contributed_by_id": user_cache.get(ic.get("contributed_by")),
            "contributed_at": ic.get("contributed_at"),
        },
    )

print("🖼 Imported image contributions.")
print("✅ Migration complete!")
