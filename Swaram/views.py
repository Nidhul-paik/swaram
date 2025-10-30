from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, HttpResponse, FileResponse
from django.utils import timezone
from django.conf import settings
from django.db import transaction
from .models import User, AudioFile, ImageContribution
import os, csv, shutil
from functools import wraps
from django.contrib.auth.hashers import make_password
from django.contrib.auth import get_user_model
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.urls import reverse


FINAL_DATA_DIR = os.path.join(settings.BASE_DIR, 'final_verified_data')
CONTRIBUTION_IMAGE_DIR = os.path.join(settings.BASE_DIR, 'contribution_assets', 'images')
CONTRIBUTION_AUDIO_DIR = os.path.join(settings.BASE_DIR, 'contribution_assets', 'audio_submissions')
FINAL_CONTRIBUTION_DIR = os.path.join(settings.BASE_DIR, 'final_contribution_data')


# Helper Decorator
def admin_required(view_func):
    decorated_view_func = user_passes_test(lambda u: u.is_authenticated and u.role == 'admin')(view_func)
    return decorated_view_func


# --- Authentication ---
def register_view(request):
    if request.user.is_authenticated:
        return redirect('landing_page')
    if request.method == 'POST':
        username = request.POST['username']
        full_name = request.POST['full_name']
        password = request.POST['password']
        if not username or not full_name or not password:
            messages.error(request, 'All fields are required.')
            return redirect('register')
        if User.objects.filter(username=username).exists():
            messages.warning(request, 'Username already exists.')
        else:
            user = User.objects.create_user(username=username, password=password, full_name=full_name, role='employee')
            messages.success(request, 'Account created! You can log in.')
            return redirect('login')
    return render(request, 'register.html')





@login_required
def logout_view(request):
    user = request.user
    AudioFile.objects.filter(status='assigned', assigned_to=user).update(status='pending', assigned_to=None)
    ImageContribution.objects.filter(status='assigned', assigned_to=user).update(status='pending', assigned_to=None)
    logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('login')


# --- Landing Pages ---
@login_required
def landing_page(request):
    if request.user.role == 'admin':
        return redirect('admin_dashboard')
    return render(request, 'landing_page.html')


# --- Employee Workspace ---
@login_required
def employee_workspace(request):
    user = request.user
    if user.role != 'employee':
        return redirect('login')

    if request.method == 'POST':
        file_id = request.POST['file_id']
        corrected_text = request.POST['transcription']
        file = get_object_or_404(AudioFile, id=file_id, assigned_to=user)
        file.corrected_transcription = corrected_text
        file.status = 'completed'
        file.verified_by = user
        file.verified_at = timezone.now()
        file.assigned_to = None
        file.save()
        messages.success(request, 'Transcription submitted for admin review.')
        return redirect('employee_workspace')

    current_file = AudioFile.objects.filter(status='assigned', assigned_to=user).first()
    if not current_file:
        next_file = AudioFile.objects.filter(status='pending').order_by('id').first()
        if next_file:
            next_file.status = 'assigned'
            next_file.assigned_to = user
            next_file.save()
            current_file = next_file
    return render(request, 'employee_workspace.html', {'audio_file': current_file})


# --- Admin Dashboard ---
@admin_required
def admin_dashboard(request):
    employees = User.objects.filter(role='employee')
    return render(request, 'admin_dashboard.html', {'employee_users': employees})


@admin_required
def admin_verify_transcription(request, file_id):
    file_to_verify = get_object_or_404(AudioFile, id=file_id)
    if request.method == 'POST':
        final_transcription = request.POST.get('transcription', file_to_verify.corrected_transcription)
        if verify_and_export_file(file_to_verify, final_transcription):
            messages.success(request, f"{file_to_verify.filename} verified and exported!")
        else:
            messages.error(request, f"Error exporting {file_to_verify.filename}")
        return redirect('admin_dashboard')
    return render(request, 'admin_verify_transcription.html', {'audio_file': file_to_verify})


# --- Utility ---
def verify_and_export_file(file_obj, final_transcription):
    try:
        os.makedirs(os.path.join(FINAL_DATA_DIR, 'audio_files'), exist_ok=True)
        csv_path = os.path.join(FINAL_DATA_DIR, 'verified_metadata.csv')
        if not os.path.exists(csv_path):
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['final_filename', 'final_transcription', 'verified_at'])

        new_filename = f"{file_obj.source_folder}_{file_obj.filename}"
        src = os.path.join(settings.BASE_DIR, 'raw_data', file_obj.source_folder, file_obj.filename)
        dst = os.path.join(FINAL_DATA_DIR, 'audio_files', new_filename)
        shutil.copy(src, dst)

        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([new_filename, final_transcription, timezone.now().strftime("%Y-%m-%d %H:%M:%S")])

        file_obj.corrected_transcription = final_transcription
        file_obj.status = 'verified'
        file_obj.verified_at = timezone.now()
        file_obj.save()
        return True
    except Exception as e:
        print(f"Error exporting {file_obj.id}: {e}")
        return False

# def login_view(request):
#     if request.method == 'POST':
#         username = request.POST.get('username')
#         password = request.POST.get('password')

#         user = authenticate(request, username=username, password=password)
#         if user :
#             login(request, user)
#             messages.success(request, "Login successful!")
#             return redirect('landing_page')
#         else:
#             messages.error(request, "Invalid username or password.")
#             return redirect('login')

#     return render(request, 'login.html')

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from werkzeug.security import check_password_hash  # Flask password checking

User = get_user_model()

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        # --- 1️⃣ Try normal Django authentication ---
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            messages.success(request, "Login successful!")
            return redirect('landing_page')

        # --- 2️⃣ Fallback to Flask hash verification ---
        try:
            user_obj = User.objects.get(username=username)

            # Detect old Flask hash formats
            if user_obj.password.startswith("scrypt:") or user_obj.password.startswith("pbkdf2:"):
                if check_password_hash(user_obj.password, password):
                    # ✅ Flask password matched — migrate to Django format
                    user_obj.password = make_password(password)
                    user_obj.save(update_fields=["password"])

                    login(request, user_obj)
                    messages.success(
                        request,
                        "Login successful! (Password migrated from Flask to Django format)"
                    )
                    return redirect('landing_page')

        except User.DoesNotExist:
            pass

        # --- 3️⃣ If both methods fail ---
        messages.error(request, "Invalid username or password.")
        return redirect('login')

    return render(request, 'login.html')


User = get_user_model()

def register_view(request):
    if request.user.is_authenticated:
        return redirect('landing_page')

    if request.method == 'POST':
        username = request.POST.get('username')
        full_name = request.POST.get('full_name')
        password = request.POST.get('password')

        if not username or not full_name or not password:
            messages.error(request, "All fields are required.")
            return redirect('register')

        if User.objects.filter(username=username).exists():
            messages.warning(request, "Username already exists.")
            return redirect('register')

        # ✅ Use custom manager method
        user = User.objects.create_user(
            username=username,
            full_name=full_name,
            role='employee',
            password=password
        )

        messages.success(request, "Account created successfully! Please log in.")
        return redirect('login')

    return render(request, 'register.html')


@login_required
def leaderboard(request):
    # You can later replace this with real data
    return render(request, 'leaderboard.html')

# Swaram/views.py
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import ImageContribution
from django.db.models import Q
from django.db import transaction

@login_required
def contribute_workspace(request):
    user = request.user
    if not hasattr(user, 'role') or user.role != 'employee':
        return redirect('login')

    # Check if the user already has an assigned image
    current_image = ImageContribution.objects.filter(status='assigned', assigned_to=user).first()
    if current_image:
        return render(request, 'contribute_workspace.html', {'image_file': current_image})

    # Atomically assign a new image if any pending exists
    with transaction.atomic():
        next_image = (
            ImageContribution.objects
            .select_for_update(skip_locked=True)
            .filter(status='pending')
            .order_by('?')
            .first()
        )

        if next_image:
            next_image.status = 'assigned'
            next_image.assigned_to = user
            next_image.save()
            return render(request, 'contribute_workspace.html', {'image_file': next_image})

    # No pending images left
    return render(request, 'contribute_workspace.html', {'image_file': None})

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Sum, Count
from .models import AudioFile, ImageContribution, User  # assuming these exist

@login_required
def api_leaderboard(request):
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    # --- Transcription Leaderboard ---
    transcription_leaders = (
        AudioFile.objects.filter(status='verified', verified_by__role='employee')
        .values('verified_by__full_name')
        .annotate(total_duration=Sum('duration_ms'))
        .order_by('-total_duration')[:10]
    )

    # --- Image Contribution Leaderboard ---
    contribution_leaders = (
        ImageContribution.objects.filter(status='verified', contributed_by__role='employee')
        .values('contributed_by__full_name')
        .annotate(total_contributions=Count('id'))
        .order_by('-total_contributions')[:10]
    )

    # Format response
    response_data = {
        'transcription_leaders': list(transcription_leaders),
        'contribution_leaders': list(contribution_leaders),
    }

    return JsonResponse(response_data)

from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import os

from .models import ImageContribution

@csrf_exempt  # only if you are testing; for production, use CSRF token in form
def contribute_submit(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    if request.method == 'POST':
        image_id = request.POST.get('image_id')
        audio_data = request.FILES.get('audio_data')
        image_filename = request.POST.get('image_filename')

        if not all([image_id, audio_data, image_filename]):
            return JsonResponse({'error': 'Missing data'}, status=400)

        audio_filename = f"{os.path.splitext(image_filename)[0]}.wav"
        save_dir = os.path.join(settings.MEDIA_ROOT, 'contribution_audio')
        os.makedirs(save_dir, exist_ok=True)

        save_path = os.path.join(save_dir, audio_filename)
        with open(save_path, 'wb+') as destination:
            for chunk in audio_data.chunks():
                destination.write(chunk)

        try:
            contribution = ImageContribution.objects.get(id=image_id, assigned_to=request.user)
            contribution.audio_filename = audio_filename
            contribution.status = 'completed'
            contribution.contributed_by = request.user
            contribution.contributed_at = timezone.now()
            contribution.assigned_to = None
            contribution.save()

            return JsonResponse({'message': 'Contribution submitted successfully!'})
        except ImageContribution.DoesNotExist:
            return JsonResponse({'error': 'Contribution not found or not assigned to you'}, status=404)

    return JsonResponse({'error': 'Invalid request method'}, status=405)

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.decorators import login_required
from Swaram.models import User, AudioFile, ImageContribution

@login_required
def admin_delete_user(request, user_id):
    # Allow only admin users
    if not request.user.is_authenticated or request.user.role != 'admin':
        return redirect('login')

    user_to_delete = get_object_or_404(User, id=user_id)

    # Prevent admin from deleting their own account
    if user_to_delete.id == request.user.id:
        messages.error(request, "You cannot delete your own account.")
        return redirect('admin_dashboard')

    # Use a transaction to ensure atomic operations
    with transaction.atomic():
        # Reset audio files assigned or completed by this user
        AudioFile.objects.filter(assigned_to=user_to_delete).update(
            status='pending', assigned_to=None
        )
        AudioFile.objects.filter(status='completed', verified_by=user_to_delete).update(
            status='pending',
            corrected_transcription=None,
            verified_by=None,
            verified_at=None
        )

        # Reset image contributions assigned or completed by this user
        ImageContribution.objects.filter(assigned_to=user_to_delete).update(
            status='pending', assigned_to=None
        )
        ImageContribution.objects.filter(status='completed', contributor=user_to_delete).update(
            status='pending',
            contributed_by=None,
            contributed_at=None,
            audio_filename=None
        )

        # Finally, delete the user
        user_to_delete.delete()

    messages.success(request, "User deleted successfully. Their work was returned to the queue.")
    return redirect('admin_dashboard')


import os
import csv
from datetime import datetime
from django.conf import settings
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from Swaram.models import AudioFile, User

@login_required
def api_stats(request):
    # Check user authentication
    if not request.user.is_authenticated:
        return JsonResponse({}, status=403)

    # Database queries
    total = AudioFile.objects.count()
    pending = AudioFile.objects.filter(status='pending').count()
    completed = AudioFile.objects.filter(status='completed').count()
    user_count = User.objects.filter(role='employee').count()

    # File-based verification stats
    verified_count, verified_today_count = 0, 0
    final_data_dir = getattr(settings, 'FINAL_DATA_DIR', None)
    
    if final_data_dir:
        verified_audio_path = os.path.join(final_data_dir, 'audio_files')
        if os.path.isdir(verified_audio_path):
            verified_count = len([name for name in os.listdir(verified_audio_path) if name.endswith('.wav')])

        csv_path = os.path.join(final_data_dir, 'verified_metadata.csv')
        if os.path.isfile(csv_path):
            today_str = datetime.now().strftime('%Y-%m-%d')
            try:
                with open(csv_path, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('verified_at') and row['verified_at'].strip().startswith(today_str):
                            verified_today_count += 1
            except Exception as e:
                print(f"Error reading CSV for daily stats: {e}")

    final_total = max(total, verified_count)

    data = {
        "total": final_total,
        "pending": pending,
        "completed": completed,
        "verified": verified_count,
        "verified_today": verified_today_count,
        "user_count": user_count,
    }

    return JsonResponse(data)


import os
from django.conf import settings
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from Swaram.models import ImageContribution

@login_required
def api_stats_contribution(request):
    # Check authentication
    if not request.user.is_authenticated:
        return JsonResponse({}, status=403)

    # Database counts
    pending = ImageContribution.objects.filter(status='pending').count()
    completed = ImageContribution.objects.filter(status='completed').count()

    # Filesystem verified count
    verified_count = 0
    final_contribution_dir = getattr(settings, 'FINAL_CONTRIBUTION_DIR', None)

    if final_contribution_dir:
        verified_audio_dir = os.path.join(final_contribution_dir, 'audio')
        if os.path.isdir(verified_audio_dir):
            verified_count = len([
                name for name in os.listdir(verified_audio_dir)
                if name.endswith('.wav')
            ])

    # True total = DB + verified filesystem count
    final_total = pending + completed + verified_count

    data = {
        "total": final_total,
        "pending": pending,
        "completed": completed,
        "verified": verified_count,
    }

    return JsonResponse(data)


from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from Swaram.models import AudioFile, ImageContribution, User  # adjust import path if needed
from django.db.models import F

# -----------------------------------------------------------------
# 1️⃣ /api/review_files → Lists all completed audio files for admin review
# -----------------------------------------------------------------
@login_required
def api_review_files(request):
    if request.user.role != 'admin':
        return JsonResponse({"error": "Unauthorized"}, status=403)

    files = (
        AudioFile.objects
        .filter(status='completed', verified_by__isnull=False)
        .select_related('verified_by')
        .order_by('verified_at')
        .values(
            'id',
            'source_folder',
            'filename',
            'verified_at',
            employee_name=F('verified_by__full_name')
        )
    )
    return JsonResponse(list(files), safe=False)

# -----------------------------------------------------------------
# 2️⃣ /api/locked_files → Lists all files currently assigned ("locked")
# -----------------------------------------------------------------
@login_required
def api_locked_files(request):
    if request.user.role != 'admin':
        return JsonResponse({"error": "Unauthorized"}, status=403)

    transcription_locks = (
        AudioFile.objects
        .filter(status='assigned', assigned_to__isnull=False)
        .select_related('assigned_to')
        .values(
            'id',
            'filename',
            employee_name=F('assigned_to__full_name')
        )
    )

    contribution_locks = (
        ImageContribution.objects
        .filter(status='assigned', assigned_to__isnull=False)
        .select_related('assigned_to')
        .values(
            'id',
            filename=F('image_filename'),
            employee_name=F('assigned_to__full_name')
        )
    )

    return JsonResponse({
        "transcription": list(transcription_locks),
        "contribution": list(contribution_locks)
    })

# -----------------------------------------------------------------
# 3️⃣ /api/contribution_reviews → Lists all completed image contributions
# -----------------------------------------------------------------
@login_required
def api_contribution_reviews(request):
    if request.user.role != 'admin':
        return JsonResponse({"error": "Unauthorized"}, status=403)

    reviews = (
        ImageContribution.objects
        .filter(status='completed', contributed_by__isnull=False)
        .select_related('contributed_by')
        .order_by('contributed_at')
        .values(
            'id',
            'image_filename',
            'audio_filename',
            'status',
            'contributed_at',
            contributor_name=F('contributed_by__full_name')
        )
    )

    return JsonResponse(list(reviews), safe=False)


@login_required
def admin_verify_all_transcription(request):
    user = request.user
    if user.role != 'admin':
        return redirect('login')

    # Get all files marked as completed
    files_to_verify = AudioFile.objects.filter(status='completed')

    verified_count = 0
    error_count = 0

    for file_info in files_to_verify:
        try:
            # Assuming verify_and_export_file(file_obj, corrected_text)
            if verify_and_export_file(file_info, file_info.corrected_transcription):
                verified_count += 1
            else:
                error_count += 1
        except Exception as e:
            print(f"Verification error for {file_info.filename}: {e}")
            error_count += 1

    # Prepare user feedback message
    message = f"Bulk verification complete. {verified_count} files exported successfully."
    if error_count > 0:
        message += f" {error_count} files failed."

    messages.success(request, message if error_count == 0 else message)
    return redirect('admin_dashboard')





@login_required
def admin_release_locks(request):
    # Ensure only admin users can do this
    if request.user.role != 'admin':
        messages.error(request, "Unauthorized access.")
        return redirect('login')

    # Only respond to POST requests
    if request.method == 'POST':
        # Release all locked (assigned) files
        AudioFile.objects.filter(status='assigned').update(status='pending', assigned_to=None)
        ImageContribution.objects.filter(status='assigned').update(status='pending', assigned_to=None)

        messages.success(request, "All locked files have been released and returned to the pending queue.")
        return redirect('admin_dashboard')

    # If accessed via GET — just redirect safely
    return redirect('admin_dashboard')
