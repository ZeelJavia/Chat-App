from django.dispatch import receiver
from django.db.models.signals import post_save, pre_save
from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from .models import Profile

@receiver(post_save, sender=User)       
def user_postsave(sender, instance, created, **kwargs):
    """
    Signal handler that executes after a User instance is saved.
    
    This function handles two main cases:
    1. For newly created users: automatically creates a Profile instance
    2. For existing users: manages email verification status in django-allauth
    
    Parameters:
    - sender: The model class (User)
    - instance: The actual User instance that was saved
    - created: Boolean flag indicating if this is a new user (True) or an update (False)
    - kwargs: Additional keyword arguments
    """
    user = instance
    
    # add profile if user is created
    if created:
        Profile.objects.create(
            user = user,
        )
    else:
        # update allauth emailaddress if exists 
        try:
            email_address = EmailAddress.objects.get_primary(user)
            if email_address.email != user.email:
                email_address.email = user.email
                email_address.verified = False
                email_address.save()
        except:
            # if allauth emailaddress doesn't exist create one
            EmailAddress.objects.create(
                user = user,
                email = user.email, 
                primary = True,
                verified = False
            )
        
        
@receiver(pre_save, sender=User)
def user_presave(sender, instance, **kwargs):
    """
    Signal handler that executes before a User instance is saved.
    
    This function ensures usernames are always stored in lowercase,
    preventing case-sensitivity issues with usernames.
    
    Parameters:
    - sender: The model class (User)
    - instance: The User instance about to be saved
    - kwargs: Additional keyword arguments
    """
    if instance.username:
        instance.username = instance.username.lower()