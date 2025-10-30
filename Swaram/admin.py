# Swaram/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import User, AudioFile, ImageContribution

@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ('Extra', {'fields': ('full_name','role','api_token')}),
    )
    list_display = ('username','full_name','role','is_staff')

admin.site.register(AudioFile)
admin.site.register(ImageContribution)
