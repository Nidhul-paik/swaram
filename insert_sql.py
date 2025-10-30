# import_sqlite_to_postgres.py
import json
from django.utils import timezone
from Swaram.models import User, AudioFile, ImageContribution

with open("sqlite_data.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print("🚀 Starting import...")

# --- USERS ---
for u in data.get("users", []):
    user, created = User.objects.get_or_create(
        username=u["username"],
        defaults={
            "password": u["password"],  # already hashed
            "full_name": u["full_name"],
            "role": u["role"],
            "api_token": u.get("api_token"),
        }
    )
    if created:
        print(f"✅ Added user: {user.username}")
    else:
        print(f"⚠️ User exists: {user.username}")

# --- AUDIO FILES ---
for a in data.get("audio_files", []):
    assigned_to = User.objects.filter(id=a["assigned_to"]).first() if a.get("assigned_to") else None
    verified_by = User.objects.filter(id=a["verified_by"]).first() if a.get("verified_by") else None

    AudioFile.objects.get_or_create(
        source_folder=a["source_folder"],
        filename=a["filename"],
        defaults={
            "original_transcription": a["original_transcription"],
            "duration_ms": a.get("duration_ms"),
            "corrected_transcription": a.get("corrected_transcription"),
            "status": a["status"],
            "assigned_to": assigned_to,
            "verified_by": verified_by,
            "verified_at": a.get("verified_at") or None,
        }
    )

print("🎧 Imported all audio files.")

# --- IMAGE CONTRIBUTIONS ---
for ic in data.get("image_contributions", []):
    assigned_to = User.objects.filter(id=ic["assigned_to"]).first() if ic.get("assigned_to") else None
    contributed_by = User.objects.filter(id=ic["contributed_by"]).first() if ic.get("contributed_by") else None

    ImageContribution.objects.get_or_create(
        image_filename=ic["image_filename"],
        defaults={
            "audio_filename": ic.get("audio_filename"),
            "status": ic.get("status", "pending"),
            "assigned_to": assigned_to,
            "contributed_by": contributed_by,
            "contributed_at": ic.get("contributed_at") or None,
        }
    )

print("🖼 Imported all image contributions.")
print("✅ Migration complete!")
