from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Profile

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
    instance.profile.save()

# --- Google Auth Signal ---
import requests
from django.core.files.base import ContentFile
from allauth.account.signals import user_signed_up
from allauth.socialaccount.models import SocialAccount

@receiver(user_signed_up)
def populate_profile_from_google(request, user, **kwargs):
    """
    When a user signs up via Google, fetch their profile picture.
    """
    try:
        # Check if user has a google account linked
        social_account = SocialAccount.objects.filter(user=user, provider='google').first()
        
        if social_account:
            # Google returns 'picture' in extra_data
            data = social_account.extra_data
            picture_url = data.get('picture')
            
            if picture_url:
                # Download image
                response = requests.get(picture_url)
                if response.status_code == 200:
                    # Save to Profile
                    if hasattr(user, 'profile'):
                        filename = f"google_{user.id}.jpg"
                        user.profile.profile_image.save(filename, ContentFile(response.content), save=True)
    except Exception as e:
        print(f"Error fetching Google profile picture: {e}")
