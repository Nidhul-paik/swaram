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


import random
from django.core.mail import send_mail
from .models import EmailOTP

from django.conf import settings

def send_otp_to_email(email):
    otp = str(random.randint(100000, 999999))
    EmailOTP.objects.filter(email=email).delete()
    EmailOTP.objects.create(email=email, otp=otp)
    message = f"""
                Your One-Time Password for the ICFOSS Swaram platform is: {otp}

                This code is valid for 5 minutes.

                If you did not request this, please ignore this email.

                Thank you,
                The ICFOSS Swaram Team
                """
    send_mail(
        subject="Your OTP for Registration",
        message=message,
        from_email=settings.EMAIL_HOST_USER,   # ✅ use your configured Gmail
        recipient_list=[email],
        fail_silently=False,
    )
    return otp



import os
import time
from django.core.cache import cache
from django.conf import settings


class LiveGamificationTracker:
    # Keys
    USER_SCORE_KEY = "gamify_score_{}_{}" # user_id, date
    ACTIVE_USERS_SET = "gamify_active_users"
    GLOBAL_STATS_KEY = "gamify_global_stats"
    
    # Config
    USER_TIMEOUT = 300 # 5 minutes offline = removed from live list

    def _get_date_key(self):
        return time.strftime("%Y%m%d") # Resets every day at midnight

    def increment_score(self, user):
        """
        Atomically increments the user's score on the server.
        Stable: Refreshes won't reset this number.
        """
        if not user.is_authenticated:
            return 0

        date_key = self._get_date_key()
        cache_key = self.USER_SCORE_KEY.format(user.id, date_key)
        
        # Initialize if not exists
        if cache.get(cache_key) is None:
            cache.set(cache_key, 0, timeout=86400) # 24 hours

        # Atomic increment (Thread safe)
        new_score = cache.incr(cache_key)
        
        # Mark user as active
        self._mark_active(user)
        
        return new_score

    def _mark_active(self, user):
        active_users = cache.get(self.ACTIVE_USERS_SET, set())
        active_users.add(user.id)
        cache.set(self.ACTIVE_USERS_SET, active_users, self.USER_TIMEOUT)

    def get_live_data(self, current_user_id=None):
        """
        Returns stable leaderboard data.
        """
        active_ids = cache.get(self.ACTIVE_USERS_SET, set())
        date_key = self._get_date_key()
        
        leaderboard = []
        stale_ids = set()
        total_saves_today = 0

        for uid in active_ids:
            # Fetch score directly from server cache
            score = cache.get(self.USER_SCORE_KEY.format(uid, date_key))
            
            if score is not None:
                # We need the username. Since we only have ID, we try to fetch from cache or DB
                # Optimisation: For now, we assume username is not strictly needed for calculation 
                # but we need it for display. 
                # In a real app, you cache the username mapping too.
                from Swaram.models import User  # or whatever your custom user model is called
                try:
                    u = User.objects.get(id=uid)
                    leaderboard.append({
                        'id': uid,
                        'username': u.username,
                        'count': score
                    })
                    total_saves_today += score
                except User.DoesNotExist:
                    stale_ids.add(uid)
            else:
                # Score expired (user inactive for 24h)
                stale_ids.add(uid)

        # Cleanup
        if stale_ids:
            cache.set(self.ACTIVE_USERS_SET, active_ids - stale_ids, self.USER_TIMEOUT)

        # Sort: Highest Score first
        leaderboard.sort(key=lambda x: x['count'], reverse=True)

        # Calculate Rankings for the requested user
        my_rank = 0
        rival = None
        
        if current_user_id:
            for idx, entry in enumerate(leaderboard):
                if entry['id'] == current_user_id:
                    my_rank = idx + 1
                    if idx > 0:
                        rival = leaderboard[idx - 1]
                    break

        return {
            'active_users': leaderboard,
            'active_count': len(leaderboard),
            'total_saved': total_saves_today,
            'my_rank': my_rank,
            'rival': rival
        }

live_tracker = LiveGamificationTracker()