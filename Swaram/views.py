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

@login_required
def home_page(request):
    if request.user.role == 'admin':
        return redirect('admin_dashboard')
    return render(request, 'home.html')

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



def login_view(request):
    if request.method == 'POST':

        # ------------------------------------------------------------------
        # STEP A – NORMAL LOGIN
        # ------------------------------------------------------------------
        if ('username' in request.POST and
            'password' in request.POST and
            'send_otp' not in request.POST):

            username = request.POST.get('username')
            password = request.POST.get('password')

            user = authenticate(request, username=username, password=password)
            if user:
                login(request, user)
                messages.success(request, "Login successful!")
                return redirect('intern_contribution')

            # ----- Try old Flask-style password hashes -----
            try:
                user_obj = User.objects.get(username=username)
                if user_obj.password.startswith(("scrypt:", "pbkdf2:")):
                    if check_password_hash(user_obj.password, password):
                        user_obj.password = make_password(password)
                        user_obj.save(update_fields=["password"])
                        login(request, user_obj)
                        messages.success(request,
                                         "Login successful! (Password migrated)")
                        return redirect('intern_contribution')
            except User.DoesNotExist:
                pass

            messages.error(request, "Invalid username or password.")
            return redirect('login')

        # ------------------------------------------------------------------
        # STEP B – SEND OTP
        # ------------------------------------------------------------------
        elif 'send_otp' in request.POST:
            email = request.POST.get('email')
            if not User.objects.filter(email=email).exists():
                messages.error(request, "No user found with this email.")
                return redirect('login')

            send_otp_to_email(email)
            messages.success(request, f"OTP sent to {email}.")
            return render(request, 'login.html', {
                'show_otp_form': True,
                'email': email
            })

        # ------------------------------------------------------------------
        # STEP C – VERIFY OTP
        # ------------------------------------------------------------------
        elif 'verify_otp' in request.POST:
            email = request.POST.get('email')
            otp = ''.join(request.POST.get(f'otp_digit_{i}', '') for i in range(1, 7))

            try:
                otp_rec = EmailOTP.objects.get(email=email, otp=otp)
                if otp_rec.is_expired():
                    raise ValueError("expired")

                # OTP is valid → show reset-password page
                return render(request, 'login.html', {
                    'show_reset': True,
                    'email': email,
                    'otp': otp
                })

            except (EmailOTP.DoesNotExist, ValueError):
                messages.error(request, "Invalid or expired OTP.")
                return render(request, 'login.html', {
                    'show_otp_form': True,
                    'email': email
                })

        # ------------------------------------------------------------------
        # STEP D – RESET PASSWORD
        # ------------------------------------------------------------------
        elif 'reset_password' in request.POST:
            email = request.POST.get('email')
            otp   = request.POST.get('otp')
            pw    = request.POST.get('password')
            cpw   = request.POST.get('confirm_password')

            if pw != cpw:
                messages.error(request, "Passwords do not match.")
                return render(request, 'login.html', {
                    'show_reset': True,
                    'email': email,
                    'otp': otp
                })

            try:
                otp_rec = EmailOTP.objects.get(email=email, otp=otp)
                if otp_rec.is_expired():
                    messages.error(request, "OTP expired! Please resend OTP.")
                    return redirect('login')

                user = User.objects.get(email=email)
                user.set_password(pw)
                user.save()
                otp_rec.delete()

                messages.success(request,
                                 "Password reset successful! Please log in.")
                return redirect('login')

            except EmailOTP.DoesNotExist:
                messages.error(request, "Invalid OTP.")
                return render(request, 'login.html', {
                    'show_reset': True,
                    'email': email,
                    'otp': otp
                })

    # ------------------------------------------------------------------
    # GET request → normal login page
    # ------------------------------------------------------------------
    return render(request, 'login.html')

User = get_user_model()



from django.shortcuts import render, redirect
from django.contrib import messages
from .models import User
from .utils import send_otp_to_email
from .models import EmailOTP

def register_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        full_name = request.POST.get('full_name')
        email = request.POST.get('email')
        password = request.POST.get('password')

        if not all([username, full_name, email, password]):
            messages.error(request, "All fields are required.")
            return redirect('register')

        if User.objects.filter(username=username).exists():
            messages.warning(request, "Username already exists.")
            return redirect('register')

        if User.objects.filter(email=email).exists():
            messages.warning(request, "Email already exists.")
            return redirect('register')

        # ✅ Send OTP
        send_otp_to_email(email)
        request.session['pending_user'] = {
            'username': username,
            'full_name': full_name,
            'email': email,
            'password': password
        }
        messages.info(request, f"OTP sent to {email}. Please verify.")
        return redirect('verify_otp')

    return render(request, 'register.html')


from django.utils import timezone
from datetime import timedelta
from .models import EmailOTP, User
from django.contrib import messages

def verify_otp_view(request):
    pending_user = request.session.get('pending_user')
    if not pending_user:
        return redirect('register')

    email = pending_user['email']

    if request.method == 'POST':
        otp_entered = request.POST.get('otp')
        try:
            otp_obj = EmailOTP.objects.get(email=email, otp=otp_entered)
        except EmailOTP.DoesNotExist:
            messages.error(request, "Invalid OTP.")
            return redirect('verify_otp')

        if otp_obj.is_expired():
            messages.error(request, "OTP expired. Please resend.")
            return redirect('verify_otp')

        otp_obj.is_verified = True
        otp_obj.save()

        # ✅ Create user after verification
        user = User.objects.create_user(
            username=pending_user['username'],
            full_name=pending_user['full_name'],
            role='employee',
            password=pending_user['password']
        )
        user.email = email
        user.save()

        del request.session['pending_user']
        messages.success(request, "Registration successful! Please log in.")
        return redirect('login')

    return render(request, 'verify_otp.html', {'email': email})


def resend_otp_view(request):
    pending_user = request.session.get('pending_user')
    if not pending_user:
        return redirect('register')

    email = pending_user['email']

    # Check last OTP time
    last_otp = EmailOTP.objects.filter(email=email).order_by('-created_at').first()
    if last_otp and timezone.now() - last_otp.created_at < timedelta(minutes=1):
        messages.warning(request, "Please wait a minute before resending OTP.")
        return redirect('verify_otp')

    send_otp_to_email(email)
    messages.success(request, "OTP resent successfully.")
    return redirect('verify_otp')


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
# def api_leaderboard(request):
#     user = request.user
#     if not user.is_authenticated:
#         return JsonResponse({'error': 'Unauthorized'}, status=403)

#     # --- Transcription Leaderboard ---
#     transcription_leaders = (
#         AudioFile.objects.filter(status='verified', verified_by__role='employee')
#         .values('verified_by__full_name')
#         .annotate(total_duration=Sum('duration_ms'))
#         .order_by('-total_duration')[:10]
#     )

#     # --- Image Contribution Leaderboard ---
#     contribution_leaders = (
#         ImageContribution.objects.filter(status='verified', contributed_by__role='employee')
#         .values('contributed_by__full_name')
#         .annotate(total_contributions=Count('id'))
#         .order_by('-total_contributions')[:10]
#     )

#     # Format response
#     response_data = {
#         'transcription_leaders': list(transcription_leaders),
#         'contribution_leaders': list(contribution_leaders),
#     }

#     return JsonResponse(response_data)



def api_leaderboard(request):
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    # --- Transcription Leaderboard ---
    try:
        # Case 1: verified_by is a ForeignKey
        AudioFile._meta.get_field('verified_by')
        transcription_leaders = (
            AudioFile.objects.filter(status='verified', verified_by__role='employee')
            .values(full_name=F('verified_by__full_name'))
            .annotate(total_duration=Sum('duration_ms'))
            .order_by('-total_duration')[:10]
        )
    except:
        # Case 2: verified_by_id is integer field
        transcription_leaders = (
            AudioFile.objects.filter(status='verified', verified_by_id__isnull=False)
            .values('verified_by_id')
            .annotate(total_duration=Sum('duration_ms'))
            .order_by('-total_duration')[:10]
        )
        # manually attach name from User table
        user_map = {u.id: u.full_name for u in User.objects.all()}
        transcription_leaders = [
            {"full_name": user_map.get(item["verified_by_id"], "Unknown"),
             "total_duration": item["total_duration"]}
            for item in transcription_leaders
        ]

    # --- Image Contribution Leaderboard ---
    try:
        ImageContribution._meta.get_field('contributed_by')
        contribution_leaders = (
            ImageContribution.objects.filter(status='verified', contributed_by__role='employee')
            .values(full_name=F('contributed_by__full_name'))
            .annotate(total_contributions=Count('id'))
            .order_by('-total_contributions')[:10]
        )
    except:
        contribution_leaders = (
            ImageContribution.objects.filter(status='verified', contributed_by_id__isnull=False)
            .values('contributed_by_id')
            .annotate(total_contributions=Count('id'))
            .order_by('-total_contributions')[:10]
        )
        user_map = {u.id: u.full_name for u in User.objects.all()}
        contribution_leaders = [
            {"full_name": user_map.get(item["contributed_by_id"], "Unknown"),
             "total_contributions": item["total_contributions"]}
            for item in contribution_leaders
        ]

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
        ImageContribution.objects.filter(status='completed', contributed_by=user_to_delete).update(
            status='pending',
            contributed_by=None,
            contributed_at=None,
            audio_filename=None
        )

        # Finally, delete the user
        user_to_delete.delete()

    messages.success(request, "User deleted successfully. Their work was returned to the queue.")
    return redirect('admin_dashboard')

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from Swaram.models import ImageContribution

@login_required
def admin_review_contribution(request, item_id):
    # Only allow admin users
    if request.user.role != 'admin':
        return redirect('login')

    # Get the contribution item
    item = (
        ImageContribution.objects
        .select_related('contributed_by')
        .filter(id=item_id, status='completed')
        .first()
    )

    if not item:
        messages.warning(request, "This contribution is no longer available for review.")
        return redirect('admin_dashboard')

    return render(request, 'admin_verify_contribution.html', {'item': item})

def serve_contribution_asset(request, folder, filename):
    """
    Serves image/audio contribution assets (only for logged-in users).
    """

    # Define allowed folders
    allowed_folders = ['images', 'audio_submissions']
    if folder not in allowed_folders:
        raise Http404("Invalid folder")

    # Construct path inside media/contribution_assets/<folder>/
    directory = os.path.join(settings.MEDIA_ROOT, 'contribution_assets', folder)
    file_path = os.path.join(directory, filename)

    # Check if file exists
    if not os.path.exists(file_path):
        raise Http404(f"File not found: {file_path}")

    # Return file (image/audio)
    try:
        return FileResponse(open(file_path, 'rb'))
    except Exception as e:
        return HttpResponse(f"Error serving file: {e}", status=500)



# Check if the logged-in user is an admin
def is_admin(user):
    return user.is_authenticated and user.role == 'admin'



@login_required
@user_passes_test(is_admin)
@login_required
@user_passes_test(is_admin)
def verify_contribution(request, item_id):
    if request.method != "POST":
        messages.error(request, "Invalid request method.")
        return redirect("admin_dashboard")

    item = get_object_or_404(ImageContribution, id=item_id)

    if not item.audio_filename or not item.image_filename:
        messages.error(request, "Contribution not found or missing image/audio.")
        return redirect("admin_dashboard")

    # ✅ Predefine these to avoid 'referenced before assignment'
    final_image_filename = None
    final_audio_filename = None

    try:
        # Paths
        FINAL_CONTRIBUTION_DIR = os.path.join(settings.BASE_DIR, "final_contributions")
        CONTRIBUTION_IMAGE_DIR = os.path.join(settings.BASE_DIR, "media", "contribution_assets", "images")
        CONTRIBUTION_AUDIO_DIR = os.path.join(settings.BASE_DIR, "media", "contribution_assets", "audio_submissions")

        os.makedirs(os.path.join(FINAL_CONTRIBUTION_DIR, "images"), exist_ok=True)
        os.makedirs(os.path.join(FINAL_CONTRIBUTION_DIR, "audio"), exist_ok=True)

        # Filenames
        base_filename, image_ext = os.path.splitext(item.image_filename)
        final_image_filename = f"{base_filename}{image_ext}"
        final_audio_filename = f"{base_filename}.wav"

        # Paths for debugging
        src_image = os.path.join(CONTRIBUTION_IMAGE_DIR, item.image_filename)
        src_audio = os.path.join(CONTRIBUTION_AUDIO_DIR, item.audio_filename)

        print("DEBUG: Image exists?", os.path.exists(src_image), src_image)
        print("DEBUG: Audio exists?", os.path.exists(src_audio), src_audio)

        # Move files only if they exist
        if os.path.exists(src_image):
            shutil.move(src_image, os.path.join(FINAL_CONTRIBUTION_DIR, "images", final_image_filename))
        else:
            raise FileNotFoundError(f"Image not found: {src_image}")

        if os.path.exists(src_audio):
            shutil.move(src_audio, os.path.join(FINAL_CONTRIBUTION_DIR, "audio", final_audio_filename))
        else:
            raise FileNotFoundError(f"Audio not found: {src_audio}")

        # Update DB
        item.status = "verified"
        item.save()

        messages.success(request, f"✅ Contribution '{item.image_filename}' verified successfully.")
    except Exception as e:
        print(f"❌ Error verifying contribution {item_id}: {e}")
        messages.error(request, f"Error verifying contribution: {e}")

    return redirect("admin_dashboard")




# Helper decorator: ensure admin access
def admin_required(view_func):
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff)(view_func)

@login_required
@admin_required
def reject_contribution(request, item_id):
    if request.method != "POST":
        return redirect('admin_dashboard')

    contribution = get_object_or_404(ImageContribution, id=item_id)

    # Try removing the audio file
    if contribution.audio_filename:
        audio_path = os.path.join(settings.CONTRIBUTION_AUDIO_DIR, contribution.audio_filename)
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
        except OSError as e:
            print(f"Error deleting rejected audio file: {e}")

    # Reset contribution fields
    contribution.status = 'pending'
    contribution.audio_filename = None
    contribution.contributed_by = None
    contribution.contributed_at = None
    contribution.assigned_to = None
    contribution.save()

    messages.info(request, 'Contribution rejected and returned to the queue.')
    return redirect('admin_dashboard')

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

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from .models import User, EmailOTP
from .utils import send_otp_to_email



# STEP 2: OTP verification page
def verify_reset_otp(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        otp = request.POST.get('otp')

        try:
            record = EmailOTP.objects.get(email=email, otp=otp)
            if record.is_expired():
                messages.error(request, "OTP expired. Please resend OTP.")
                return redirect('password_reset')
            return render(request, 'set_new_password.html', {'email': email})
        except EmailOTP.DoesNotExist:
            messages.error(request, "Invalid OTP.")
            return render(request, 'verify_otp.html', {'email': email})

    return redirect('password_reset')


# STEP 3: Resend OTP
def resend_reset_otp(request):
    email = request.GET.get('email')
    if email:
        send_otp_to_email(email)
        messages.success(request, f"New OTP sent to {email}.")
        return render(request, 'verify_otp.html', {'email': email})
    messages.error(request, "Invalid email.")
    return redirect('password_reset')



def set_new_password(request):
    email = request.GET.get('email')
    otp = request.GET.get('otp')

    if request.method == 'POST' and 'reset_password' in request.POST:
        # === HANDLE PASSWORD RESET ===
        email = request.POST.get('email')
        otp = request.POST.get('otp')
        pw = request.POST.get('password')
        cpw = request.POST.get('confirm_password')

        if pw != cpw:
            messages.error(request, "Passwords do not match.")
            return render(request, 'new_reset_password.html', {
                'email': email,
                'otp': otp
            })

        try:
            otp_rec = EmailOTP.objects.get(email=email, otp=otp)
            if otp_rec.is_expired():
                messages.error(request, "OTP expired.")
                return redirect('login')

            user = User.objects.get(email=email)
            user.set_password(pw)
            user.save()
            otp_rec.delete()

            messages.success(request, "Password reset successful! Please log in.")
            return redirect('login')

        except (EmailOTP.DoesNotExist, User.DoesNotExist):
            messages.error(request, "Invalid request.")
            return redirect('login')

    # === GET request: show form ===
    if not email or not otp:
        return redirect('login')

    return render(request, 'new_reset_password.html', {
        'email': email,
        'otp': otp
    })




#-------- intern contribution---------

import os
import pandas as pd
from django.shortcuts import render, redirect
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import Intern
from filelock import FileLock 
import os
import csv
import shutil
import json
from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.views.decorators.csrf import ensure_csrf_cookie
from .models import Intern

# def delete_audio_and_row(user, filename, chunks_path, metadata_path):
#     """Helper: move deleted audio & remove from CSV."""
#     df = pd.read_csv(metadata_path)

#     # Find and remove matching row
#     match = df[df['filename'] == filename]
#     if not match.empty:
#         # Move file to deleted folder
#         deleted_root = os.path.join(settings.BASE_DIR, "intern_data", "deleted")
#         os.makedirs(deleted_root, exist_ok=True)

#         src_path = os.path.join(chunks_path, filename)
#         deleted_path = os.path.join(deleted_root, f"{user.username}_{filename}")

#         if os.path.exists(src_path):
#             shutil.move(src_path, deleted_path)

#         # Drop row and save CSV
#         df = df[df['filename'] != filename]
#         df.to_csv(metadata_path, index=False)









@login_required
@ensure_csrf_cookie
def intern_contribution(request):
    user = request.user
    print(f"=== REQUEST START: {request.method} from {user.username} ===")

    try:
        intern = Intern.objects.get(user=user)
        print(f"DEBUG: Found intern - {intern.folder_name}")
    except Intern.DoesNotExist:
        print("DEBUG: Intern not found")
        return render(request, "interns_workspace.html", {"access_denied": True})

    folder_path = os.path.join(settings.MEDIA_ROOT, 'intern_data', intern.folder_name)
    chunks_path = os.path.join(folder_path, "05_final_chunks")
    spect_path = os.path.join(folder_path, "06_spectrograms")
    metadata_path = os.path.join(folder_path, "metadata.csv")

    print(f"DEBUG: Folder: {folder_path} -> {os.path.exists(folder_path)}")
    print(f"DEBUG: Chunks: {chunks_path} -> {os.path.exists(chunks_path)}")
    print(f"DEBUG: Chunks: {chunks_path} -> {os.path.exists(spect_path)}")
    print(f"DEBUG: Metadata: {metadata_path} -> {os.path.exists(metadata_path)}")

    # Count actual audio files
    actual_audio_files = []
    if os.path.exists(chunks_path):
        actual_audio_files = [f for f in os.listdir(chunks_path) if f.endswith('.wav')]
        print(f"DEBUG: Actual WAV files in chunks: {len(actual_audio_files)}")

    # Load metadata.csv with PROPER HANDLING for Windows files
    audio_data = []
    if os.path.exists(metadata_path) and os.path.exists(chunks_path):
        try:
            # First, let's fix the CSV file if needed
            clean_metadata_file(metadata_path)
            
            # Now load with proper encoding and line ending handling
            with open(metadata_path, 'r', encoding='utf-8') as csvfile:
                # Use comma delimiter (we confirmed the file uses commas)
                reader = csv.DictReader(csvfile, delimiter=',')
                print(f"DEBUG: CSV fieldnames: {reader.fieldnames}")
                
                total_rows = 0
                loaded_rows = 0
                
                for row in reader:
                    total_rows += 1
                    filename = row.get("filename", "").strip()
                    
                    if not filename:
                        continue
                    
                    # Get transcription - handle encoding issues
                    transcription = row.get("transcription", "").strip()
                    
                    # Clean the filename - remove any Windows carriage returns
                    filename = filename.replace('\r', '').replace('\n', '')
                    
                    if filename and os.path.exists(os.path.join(chunks_path, filename)):
                        audio_url = f"/media/intern_data/{intern.folder_name}/05_final_chunks/{filename}"
                        audio_data.append({
                            "filename": filename,
                            "transcription": transcription,
                            "audio_url": audio_url
                        })
                        loaded_rows += 1
                        
                        # Debug first few matches
                        if loaded_rows <= 3:
                            print(f"DEBUG: ✅ Loaded '{filename}' -> '{transcription[:50]}...'")
                
                print(f"DEBUG: CSV loading summary: {loaded_rows}/{total_rows} files loaded")
                
        except Exception as e:
            print(f"DEBUG: Error reading metadata: {e}")
            import traceback
            traceback.print_exc()
            
            # Fallback: try manual parsing
            print("DEBUG: Trying fallback parsing...")
            audio_data = load_metadata_fallback(metadata_path, chunks_path, intern.folder_name)

    print(f"DEBUG: Final audio_data count: {len(audio_data)}")
    print("=== REQUEST END ===")

    # Handle POST requests
    if request.method == "POST":
        action = request.POST.get("action")
        print(f"DEBUG: POST action received: {action}")
        
        try:
            if action == "delete":
                # return handle_delete(request, user, chunks_path, metadata_path)
                return handle_delete(request, user, intern.folder_name, chunks_path, metadata_path, spect_path, user)
            elif action == "update":
                return handle_update(request, user, metadata_path)
                
            elif action == "submit":
                # return handle_submit(request, user, chunks_path, metadata_path)
                return handle_submit(request, user, intern.folder_name, chunks_path, metadata_path, spect_path, user)
            else:
                return JsonResponse({"success": False, "error": "Unknown action"})
        except Exception as e:
            print(f"DEBUG: Error in POST handler: {e}")
            return JsonResponse({"success": False, "error": str(e)})

    return render(request, "interns_workspace.html", {
        "access_denied": False,
        "audio_data": audio_data,
        "folder_name": intern.folder_name,
        "debug_info": {
            "loaded_files": len(audio_data),
            "total_audio_files": len(actual_audio_files),
            "match_status": f"{len(audio_data)}/{len(actual_audio_files)} files matched"
        }
    })


def clean_metadata_file(metadata_path):
    """Clean the metadata file - fix Windows line endings and encoding"""
    try:
        with open(metadata_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Fix Windows line endings (CRLF -> LF)
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        
        # Remove any BOM characters
        if content.startswith('\ufeff'):
            content = content[1:]
        
        # Write back cleaned content
        with open(metadata_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"DEBUG: Cleaned metadata file - fixed line endings")
        
    except Exception as e:
        print(f"DEBUG: Error cleaning metadata file: {e}")


def load_metadata_fallback(metadata_path, chunks_path, folder_name):
    """Fallback method for problematic CSV files"""
    audio_data = []
    
    try:
        with open(metadata_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if len(lines) < 2:
            return audio_data
        
        # Parse header to find column indices
        header_line = lines[0].strip().replace('\r', '').replace('\n', '')
        headers = header_line.split(',')
        
        filename_idx = None
        transcription_idx = None
        
        for i, header in enumerate(headers):
            if 'filename' in header.lower():
                filename_idx = i
            elif 'transcription' in header.lower():
                transcription_idx = i
        
        print(f"DEBUG: Fallback - filename_idx: {filename_idx}, transcription_idx: {transcription_idx}")
        
        if filename_idx is None:
            return audio_data
        
        # Parse data rows
        for line_num, line in enumerate(lines[1:], 1):
            line = line.strip().replace('\r', '').replace('\n', '')
            if not line:
                continue
                
            values = line.split(',')
            if len(values) > filename_idx:
                filename = values[filename_idx].strip()
                transcription = values[transcription_idx].strip() if transcription_idx and len(values) > transcription_idx else ""
                
                if filename and os.path.exists(os.path.join(chunks_path, filename)):
                    audio_url = f"/media/intern_data/{folder_name}/05_final_chunks/{filename}"
                    audio_data.append({
                        "filename": filename,
                        "transcription": transcription,
                        "audio_url": audio_url
                    })
                    
                    if len(audio_data) <= 3:
                        print(f"DEBUG: Fallback loaded '{filename}'")
    
    except Exception as e:
        print(f"DEBUG: Fallback also failed: {e}")
    
    print(f"DEBUG: Fallback loaded {len(audio_data)} files")
    return audio_data

import csv
import os
import time # Keep the time import
from django.http import JsonResponse

# Make sure this clean_name function is available
def clean_name(name):
    """Remove hidden characters from filename."""
    if not name:
        return ""
    return name.replace("\ufeff", "").replace("\r", "").replace("\n", "").strip()





# (Your other functions like clean_name, handle_update, etc., remain the same)
# ...

def handle_delete(request, user, intern_folder_name, chunks_path, metadata_path, spect_path, real_user):
    """
    Deletes a row from the intern's metadata.csv and moves the corresponding
    audio file from '05_final_chunks' to the central 'deleted' folder
    located in the project's base directory.
    """
    filename = request.POST.get("filename")
    if not filename:
        return JsonResponse({"success": False, "error": "Filename not provided."})

    cleaned_filename = clean_name(filename)
    temp_path = metadata_path + ".tmp"
    rows_to_keep = []
    fieldnames = []
    file_found_in_csv = False

    try:
        # Step 1: Read the CSV and remove the corresponding row in memory.
        # This correctly handles deleting the row with all its fields (transcription, mel, etc.).
        with open(metadata_path, "r", encoding="utf-8", newline="") as infile:
            reader = csv.DictReader(infile)
            fieldnames = reader.fieldnames
            if not fieldnames:
                 # Handles case where CSV is empty or malformed
                 return JsonResponse({"success": False, "error": "Metadata file is empty or invalid."})

            for row in reader:
                # Compare cleaned filenames to avoid issues with whitespace/hidden chars
                if clean_name(row.get("filename", "")) != cleaned_filename:
                    rows_to_keep.append(row)
                else:
                    file_found_in_csv = True

        if not file_found_in_csv:
            return JsonResponse({"success": False, "error": "File not found in metadata list."})

        # Step 2: Write the updated data (without the deleted row) back to the file.
        with open(temp_path, "w", encoding="utf-8", newline="") as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows_to_keep)

        # Atomically replace the old file with the new one
        os.replace(temp_path, metadata_path)
        print(f"DEBUG: Successfully removed row for '{cleaned_filename}' from metadata.csv.")
        
        # --- Step 3: Move the audio file from 05_final_chunks to the deleted folder ---

        # 1. Define the source path of the audio file
        source_audio_path = os.path.join(chunks_path, cleaned_filename)

        # 2. Define the destination path in the project's base directory
        deleted_base_path = os.path.join(settings.BASE_DIR, 'intern_data')
        deleted_folder_path = os.path.join(deleted_base_path, 'deleted')

        # 3. Ensure this specific folder exists. (Requires permissions set in Part 2)
        os.makedirs(deleted_folder_path, exist_ok=True)

        # 4. Create a unique filename to prevent overwrites from different interns
        
        if real_user.role == "admin":
            prefix = "admin_"
        else:
            prefix = ""


        unique_deleted_filename = f"{prefix}{intern_folder_name}_{cleaned_filename}"
        destination_audio_path = os.path.join(deleted_folder_path, unique_deleted_filename)

        # 5. Move the file
        if os.path.exists(source_audio_path):
            shutil.move(source_audio_path, destination_audio_path)
            print(f"DEBUG: Moved '{source_audio_path}' to '{destination_audio_path}'")
        else:
            print(f"DEBUG: Audio file '{cleaned_filename}' not found in chunks folder, but removed from CSV.")
        

        # --- Step 4: Move the spectrogram image to deleted_image folder ---

        spectrogram_filename = cleaned_filename.replace(".wav", ".png")
        spectrogram_path = os.path.join(spect_path, spectrogram_filename)

        # Destination folder for deleted images
        deleted_image_folder = os.path.join(settings.BASE_DIR, 'intern_data', 'deleted_image')
        os.makedirs(deleted_image_folder, exist_ok=True)

        # Unique deleted image filename
        if real_user.role == "admin":
            image_prefix = "admin_"
        else:
            image_prefix = ""

        unique_deleted_image = f"{image_prefix}{intern_folder_name}_{spectrogram_filename}"
        destination_image_path = os.path.join(deleted_image_folder, unique_deleted_image)

        # Move spectrogram file
        if os.path.exists(spectrogram_path):
            shutil.move(spectrogram_path, destination_image_path)
            print(f"DEBUG: Moved spectrogram '{spectrogram_path}' → '{destination_image_path}'")
        else:
            print(f"DEBUG: Spectrogram NOT FOUND → {spectrogram_path}")

        # -----------------------------------------------------------------
        return JsonResponse({"success": True, "message": "File removed and archived successfully."})

    except PermissionError:
        # This is a critical error to catch. It tells the admin EXACTLY what's wrong.
        print("ERROR: PERMISSION DENIED. Django cannot write to the BASE_DIR/intern_data/deleted folder. You must set permissions for this folder.")
        return JsonResponse({"success": False, "error": "A server permission error occurred. Please contact an administrator."})
    except Exception as e:
        # Clean up the temp file if something else went wrong
        if os.path.exists(temp_path):
            os.remove(temp_path)
        import traceback
        traceback.print_exc()
        return JsonResponse({"success": False, "error": f"An unexpected error occurred: {e}"})
  

from .live_progress import live_tracker

def handle_update(request, user, metadata_path):
    filename = request.POST.get("filename")
    new_transcription = request.POST.get("transcription", "")

    if not filename:
        return JsonResponse({"success": False, "error": "No filename provided"})

    cleaned_filename = clean_name(filename)
    temp_path = metadata_path + ".tmp"
    rows = []
    fieldnames = []
    updated = False

    try:
        # Read first
        with open(metadata_path, "r", encoding="utf-8", newline="") as infile:
            reader = csv.DictReader(infile)
            fieldnames = reader.fieldnames
            for row in reader:
                if clean_name(row.get("filename", "")) == cleaned_filename:
                    row["transcription"] = new_transcription
                    updated = True
                rows.append(row)

        if not updated:
            return JsonResponse({"success": False, "error": "File not found for update."})

        # Write second
        with open(temp_path, "w", encoding="utf-8", newline="") as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)

        time.sleep(0.1)
        os.replace(temp_path, metadata_path)

        # ✅ LIVE PROGRESS TRACKING - Get total files count
        folder_path = os.path.dirname(metadata_path)
        chunks_path = os.path.join(folder_path, "05_final_chunks")
        total_files = 0
        if os.path.exists(chunks_path):
            total_files = len([f for f in os.listdir(chunks_path) if f.endswith('.wav')])
        
        # Record the save action
        live_tracker.record_save_action(user.username, total_files)
        print(f"📝 Live progress recorded: {user.username} saved transcription")

        return JsonResponse({"success": True, "message": "Transcription updated."})

    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return JsonResponse({"success": False, "error": f"An error occurred: {e}"})

import csv
import os
import time
import shutil
from datetime import datetime
from django.conf import settings
from django.http import JsonResponse

# (Your other functions like handle_delete, clean_name, etc., remain the same)
# ...

def handle_submit(request, user, intern_folder_name, chunks_path, metadata_path, spect_path, real_user):
   
    try:
        # 1. Define Destination Paths
        # verified_base_path = os.path.join(settings.BASE_DIR, 'intern_data', 'verified')
        # 1. Choose folder based on whether ADMIN or INTERN
        if real_user.role == "admin":
            verified_base_path = os.path.join(settings.BASE_DIR, 'intern_data', 'verified_by_admin')
        else:
            verified_base_path = os.path.join(settings.BASE_DIR, 'intern_data', 'verified')

        # timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        # unique_verified_folder_name = f"{timestamp}_{intern_folder_name}"
        # destination_path = os.path.join(verified_base_path, unique_verified_folder_name)

        destination_path = os.path.join(verified_base_path, intern_folder_name)

        # Remove old verified folder if exists (so only latest remains)
        if os.path.exists(destination_path):
            shutil.rmtree(destination_path)

        # 2. Create the new folder structure for the verified submission
        dest_chunks_path = os.path.join(destination_path, '05_final_chunks')
        dest_spect_path = os.path.join(destination_path, '06_spectrograms')
        os.makedirs(dest_chunks_path, exist_ok=True)
        os.makedirs(dest_spect_path, exist_ok=True)
        print(f"DEBUG: Created verified submission folder and chunks subdirectory: {dest_chunks_path}")
        print(f"DEBUG: Created verified submission folder and chunks subdirectory: {dest_spect_path}")


        # 3. Read the source metadata and copy files
        if not os.path.exists(metadata_path):
            return JsonResponse({"success": False, "error": "Metadata file not found. Nothing to submit."})

        new_metadata_path = os.path.join(destination_path, 'metadata.csv')
        verified_audio_count = 0

        with open(metadata_path, 'r', encoding='utf-8', newline='') as infile, \
             open(new_metadata_path, 'w', encoding='utf-8', newline='') as outfile:

            reader = csv.DictReader(infile)
            fieldnames = reader.fieldnames
            
            if not fieldnames:
                shutil.rmtree(destination_path)
                return JsonResponse({"success": False, "error": "Cannot submit an empty or invalid metadata file."})

            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()

            for row in reader:
                filename = row.get('filename', '').strip()
                if not filename:
                    continue

                source_audio_path = os.path.join(chunks_path, filename)
                dest_audio_path = os.path.join(dest_chunks_path, filename)

                # Copy SPECTROGRAM
                spect_filename = filename.replace(".wav", ".png")
                source_spect = os.path.join(spect_path, spect_filename)
                dest_spect = os.path.join(dest_spect_path, spect_filename)

                if os.path.exists(source_audio_path):
                    shutil.copy2(source_audio_path, dest_audio_path)
                    
                    verified_audio_count += 1
                     # Copy spectrogram if exists
                    if os.path.exists(source_spect):
                        shutil.copy2(source_spect, dest_spect)

                    writer.writerow(row)
                else:
                    print(f"WARNING: Audio file '{filename}' was in metadata but not found. It will not be in the final submission.")

        if verified_audio_count == 0:
            shutil.rmtree(destination_path)
            return JsonResponse({"success": False, "error": "Submission failed. No valid audio files were found to submit."})

        print(f"DEBUG: Successfully copied {verified_audio_count} files to verified folder.")


        return JsonResponse({
            "success": True,
            "message": f"Successfully saved a version with {verified_audio_count} files. You can continue working and submit again."
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"success": False, "error": f"A critical error occurred: {e}"})




def live_progress_api(request):
    """API for live user progress"""
    try:
        progress_data = live_tracker.get_live_progress()
        return JsonResponse(progress_data)
    except Exception as e:
        return JsonResponse({
            'active_users_count': 0,
            'total_saved': 0,
            'total_files': 0,
            'overall_percentage': 0,
            'active_users': [],
            'timestamp': time.time(),
            'message': 'Loading...'
        })


# from django.contrib.auth.decorators import login_required
# from django.contrib.auth.models import User
# from django.shortcuts import render
# from .models import SwaramIntern


@login_required
def interns(request):
    add_message = None
    assign_message = None

    if request.method == "POST":

        # ------------ ADD INTERN ------------
        if request.POST.get("form_type") == "add_intern":
            username = request.POST.get("username")

            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                add_message = "❌ No user found with this username."
                return render(request, "interns.html", {
                    "add_message": add_message,
                    "assign_message": assign_message,
                    "interns": Intern.objects.all()
                })

            # Check if user already an intern
            if Intern.objects.filter(user=user).exists():
                add_message = "This user is already an intern."
            else:
                Intern.objects.create(folder_name="", user=user)
                add_message = "Intern added successfully."

        # ------------ ASSIGN TASK ------------
        if request.POST.get("form_type") == "assign_task":
            intern_id = request.POST.get("intern_id")
            folder_name = request.POST.get("folder_name")

            try:
                intern = Intern.objects.get(user_id=intern_id)
                intern.folder_name = folder_name
                intern.save()
                assign_message = "✅ Task assigned successfully."

            except Intern.DoesNotExist:
                assign_message = "❌ Intern does not exist."

    return render(request, "interns.html", {
        # "interns": Intern.objects.all(),
        "add_message": add_message,
        "assign_message": assign_message,
        "interns" : Intern.objects.select_related('user').all()
    })


#----- intern contribution verifycation by admin------

def load_intern_workspace(intern):
    folder_path = os.path.join(settings.BASE_DIR, 'intern_data', 'verified', intern.folder_name)
    chunks_path = os.path.join(folder_path, "05_final_chunks")
    spect_path = os.path.join(folder_path, "06_spectrograms")
    metadata_path = os.path.join(folder_path, "metadata.csv")

    audio_data = []  # your CSV loader logic here

    return {
        "folder_path": folder_path,
        "chunks_path": chunks_path,
        "spect_path" : spect_path,
        "metadata_path": metadata_path,
        "audio_data": audio_data,
        "folder_name": intern.folder_name
    }


def verify_intern(request, intern_id):
    real_user = request.user
    intern = Intern.objects.get(id=intern_id)

    # Load paths for this intern
    workspace = load_intern_workspace(intern)
    chunks_path = workspace["chunks_path"]
    metadata_path = workspace["metadata_path"]

    print("=== VERIFY INTERN REQUEST START ===")
    print(f"Intern: {intern.user.username}")
    print(f"Chunks Path: {chunks_path}")
    print(f"Metadata Path: {metadata_path}")

    # -------------------------------
    # 1️⃣   COUNT ACTUAL AUDIO FILES
    # -------------------------------
    actual_audio_files = []
    if os.path.exists(chunks_path):
        actual_audio_files = [f for f in os.listdir(chunks_path) if f.endswith(".wav")]
        print(f"DEBUG: Actual WAV files in chunks: {len(actual_audio_files)}")

    # -------------------------------
    # 2️⃣   LOAD METADATA + MATCH AUDIO
    # -------------------------------
    audio_data = []

    if os.path.exists(metadata_path) and os.path.exists(chunks_path):
        try:
            clean_metadata_file(metadata_path)

            with open(metadata_path, "r", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile, delimiter=",")
                print(f"DEBUG: CSV fieldnames: {reader.fieldnames}")

                total_rows = 0
                loaded_rows = 0

                for row in reader:
                    total_rows += 1
                    filename = row.get("filename", "").strip().replace("\r", "").replace("\n", "")
                    transcription = row.get("transcription", "").strip()

                    if not filename:
                        continue

                    full_path = os.path.join(chunks_path, filename)

                    if os.path.exists(full_path):
                        audio_data.append({
                            "filename": filename,
                            "transcription": transcription,
                            "audio_url": f"/media/intern_data/{intern.folder_name}/05_final_chunks/{filename}"
                        })
                        loaded_rows += 1

                        if loaded_rows <= 3:
                            print(f"DEBUG: Loaded: {filename}")

                print(f"DEBUG: Loaded {loaded_rows}/{total_rows} metadata rows")

        except Exception as e:
            print("DEBUG: Metadata read error:", e)
            traceback.print_exc()
            print("DEBUG: Using fallback metadata parser...")
            audio_data = load_metadata_fallback(metadata_path, chunks_path, intern.folder_name)

    print(f"DEBUG: Final audio_data count: {len(audio_data)}")
    print("=== REQUEST END ===")

    # -------------------------------
    # 3️⃣   HANDLE POST ACTIONS (same as intern view)
    # -------------------------------
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "delete":
            return handle_delete(
                request,
                intern.user,
                intern.folder_name,
                workspace["chunks_path"],
                workspace["metadata_path"],
                workspace["spect_path"],
                real_user
            )
            
        elif action == "update":
             return handle_update(
                request,
                intern.user,
                workspace["metadata_path"]
            )

        elif action == "submit":
            return handle_submit(
                request,
                intern.user,
                intern.folder_name,
                workspace["chunks_path"],
                workspace["metadata_path"],
                workspace["spect_path"],
                real_user
            )

    # -------------------------------
    # 4️⃣   RENDER ADMIN VERIFY PAGE
    # -------------------------------
    return render(request, "intern_verify.html", {
        "intern": intern,
        "folder_name": intern.folder_name,
        "audio_data": audio_data
    })
