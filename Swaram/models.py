from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
import secrets

# ---------- Custom User Model ----------


class UserManager(BaseUserManager):
    def create_user(self, username, full_name, role, password=None):
        if not username:
            raise ValueError("Users must have a username")
        user = self.model(username=username, full_name=full_name, role=role)
        user.set_password(password)
        user.api_token = secrets.token_hex(32)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, full_name, password=None):
        user = self.create_user(username, full_name, role='admin', password=password)
        user.is_superuser = True
        user.is_staff = True
        user.save(using=self._db)
        return user


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('employee', 'Employee'),
    ]

    username = models.CharField(max_length=150, unique=True)
    full_name = models.CharField(max_length=150)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    email = models.EmailField(unique=True, null=True, blank=True)
    district = models.CharField(max_length=100, null=True, blank=True)
    phone = models.CharField(max_length=15, null=True, blank=True)
    api_token = models.CharField(max_length=64, unique=True, blank=True, null=True)

    password = models.CharField(max_length=256) 
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['full_name']

    objects = UserManager()

    def __str__(self):
        return self.username



from django.conf import settings
#------Audio Files ----------
class AudioFile(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('assigned', 'Assigned'),
        ('verified', 'Verified'),
        ('completed', 'Completed'),
    ]

    source_folder = models.CharField(max_length=255)
    filename = models.CharField(max_length=255)
    file = models.FileField(upload_to='audio_files/', null=True, blank=True)  # 👈 Add this
    original_transcription = models.TextField()
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    corrected_transcription = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='assigned_audio', on_delete=models.SET_NULL, null=True, blank=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='verified_audio', on_delete=models.SET_NULL, null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('source_folder', 'filename')

    def __str__(self):
        return f"{self.filename} ({self.status})"


# ---------- Image Contributions ----------
class ImageContribution(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('assigned', 'Assigned'),
        ('completed', 'Completed'),
        ('verified', 'Verified'),
    ]

    image_filename = models.CharField(max_length=255, unique=True)
    audio_filename = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    assigned_to = models.ForeignKey(User, related_name='image_assigned', on_delete=models.SET_NULL, null=True, blank=True)
    contributed_by = models.ForeignKey(User, related_name='image_contributed', on_delete=models.SET_NULL, null=True, blank=True)
    contributed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.image_filename

from django.db import models
from django.utils import timezone
from datetime import timedelta

class EmailOTP(models.Model):
    email = models.EmailField()
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=5)  # 5 min expiry

    def __str__(self):
        return f"{self.email} - {self.otp}"





#-----interns contribution------
class Intern(models.Model):
    # This correctly points to the 'user_id' column in the database
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    # Change the field name from 'folder' to 'folder_name' to match the database
    folder_name = models.CharField(max_length=255)

    def __str__(self):
        # The __str__ method should return a string representation of the object.
        # Using the user's username is a great, unique identifier.
        # self.name would cause an error because a 'name' field doesn't exist.
        return self.user.username

    # Optional but recommended: Tell Django the table name explicitly
    # if it can't figure it out from the app/model name.
    # Since your table is "Swaram_intern", this is a good idea.
    class Meta:
        db_table = 'Swaram_intern'