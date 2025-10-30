# Swaram/utils.py
import os
import csv
import shutil
from django.conf import settings
from datetime import datetime

FINAL_DATA_DIR = getattr(settings, 'FINAL_DATA_DIR', os.path.join(settings.BASE_DIR, 'final_verified_data'))
CONTRIBUTION_IMAGE_DIR = getattr(settings, 'CONTRIBUTION_IMAGE_DIR', os.path.join('contribution_assets', 'images'))
CONTRIBUTION_AUDIO_DIR = getattr(settings, 'CONTRIBUTION_AUDIO_DIR', os.path.join('contribution_assets', 'audio_submissions'))
FINAL_CONTRIBUTION_DIR = getattr(settings, 'FINAL_CONTRIBUTION_DIR', os.path.join(settings.BASE_DIR, 'final_contribution_data'))


def audio_path_filter(filename, source_folder):
    # Walk raw_data/<source_folder> and find file path inside 05_final_chunks folder, similar to Flask version
    search_path = os.path.join(settings.BASE_DIR, 'raw_data', source_folder)
    for root, dirs, files in os.walk(search_path):
        if '05_final_chunks' in root and filename in files:
            return os.path.relpath(os.path.join(root, filename), os.path.join(settings.BASE_DIR, 'raw_data'))
    return None


def verify_and_export_file(audio_obj, final_transcription):
    """
    audio_obj is an AudioFile model instance.
    Returns True on success, False on failure.
    """
    try:
        audio_files_dir = os.path.join(FINAL_DATA_DIR, 'audio_files')
        os.makedirs(audio_files_dir, exist_ok=True)
        csv_path = os.path.join(FINAL_DATA_DIR, 'verified_metadata.csv')
        if not os.path.exists(csv_path):
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['final_filename', 'final_transcription', 'verified_at'])

        source_path_relative = audio_path_filter(audio_obj.filename, audio_obj.source_folder)
        if not source_path_relative:
            print(f"Error: Could not find audio path for {audio_obj.filename} in {audio_obj.source_folder}")
            return False

        source_path_full = os.path.join(settings.BASE_DIR, 'raw_data', source_path_relative)
        new_filename = f"{audio_obj.source_folder}_{audio_obj.filename}"
        destination_path = os.path.join(audio_files_dir, new_filename)

        shutil.copy(source_path_full, destination_path)

        timestamp = datetime.now()
        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([new_filename, final_transcription, timestamp.strftime("%Y-%m-%d %H:%M:%S")])

        # Update model
        audio_obj.corrected_transcription = final_transcription
        audio_obj.status = 'verified'
        audio_obj.verified_at = timestamp
        audio_obj.save(update_fields=['corrected_transcription','status','verified_at'])
        return True
    except Exception as e:
        print(f"verify_and_export_file error: {e}")
        return False
