# user/models.py
from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


class UserPreference(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="preferences")

    complete_opt_out = models.BooleanField(default=False)
    contextual_advertising = models.BooleanField(default=True)

    interest_categories = models.JSONField(default=list, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} Preferences"
    


from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class ChatSession(models.Model):
    """Chat conversation session"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_sessions")
    session_id = models.CharField(max_length=100, unique=True, db_index=True)
    title = models.CharField(max_length=200, default="New Chat")
    
    started_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    message_count = models.PositiveIntegerField(default=0)
    last_ad_refresh_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['-last_activity']
    
    def __str__(self):
        return f"{self.user.username} - {self.title}"


class ChatMessage(models.Model):
    """Individual messages"""
    MESSAGE_TYPES = [('user', 'User'), ('assistant', 'Assistant')]
    
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['timestamp']

