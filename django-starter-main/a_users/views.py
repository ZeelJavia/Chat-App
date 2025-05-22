from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from allauth.account.utils import send_email_confirmation
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.contrib.auth.models import User
from django.contrib.auth.views import redirect_to_login
from django.contrib import messages
from .forms import *

def profile_view(request, username=None):
    """
    Display a user's profile.
    
    1. If username is provided, get that user's profile
    2. If no username, try to get the current user's profile
    3. If user is not logged in, redirect to login page
    
    """
    if username:
        profile = get_object_or_404(User, username=username).profile
    else:
        try:
            profile = request.user.profile
        except:
            return redirect_to_login(request.get_full_path())
    return render(request, 'a_users/profile.html', {'profile':profile})


@login_required
def profile_edit_view(request):
    """
    Edit user profile information.
    
    This function handles both displaying the profile edit form and
    processing form submissions. It also handles a special case for
    the onboarding flow.
    
    Flow:
    1. Create form instance with current profile data
    2. If POST request, validate and save form data
    3. Check if we're in onboarding flow to show appropriate UI

    """
    form = ProfileForm(instance=request.user.profile)  
    

    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=request.user.profile)
        if form.is_valid():
            form.save()
            return redirect('profile')
    
    # Check if we're in onboarding flow
    if request.path == reverse('profile-onboarding'):
        onboarding = True
    else:
        onboarding = False
      
    return render(request, 'a_users/profile_edit.html', { 'form':form, 'onboarding':onboarding })


@login_required
def profile_settings_view(request):
    """
    Display user account settings page.
    
    This function serves as a central hub for account settings including:
    - Email change
    - Username change
    - Email verification
    - Account deletion
    
    It doesn't process any data itself, just renders the settings template.
    
    """
    return render(request, 'a_users/profile_settings.html')


@login_required
def profile_emailchange(request):
    """
    Handle email address changes.
    
    This function handles three scenarios:
    1. HTMX request: Returns just the email form (for dynamic loading)
    2. POST request: Processes email change submission
    3. Other requests: Redirects to settings page
    
    During email change:
    - Validates that email isn't already in use
    - Saves the new email
    - Sets verification status to False
    - Sends confirmation email

    """
    if request.htmx:
        form = EmailForm(instance=request.user)
        return render(request, 'partials/email_form.html', {'form':form})
    
    if request.method == 'POST':
        form = EmailForm(request.POST, instance=request.user)

        if form.is_valid():
            
            # Check if the email already exists
            email = form.cleaned_data['email']
            if User.objects.filter(email=email).exclude(id=request.user.id).exists():
                messages.warning(request, f'{email} is already in use.')
                return redirect('profile-settings')
            
            form.save() 
            
            # Then Signal updates emailaddress and set verified to False
            
            # Then send confirmation email 
            send_email_confirmation(request, request.user)
            
            return redirect('profile-settings')
        else:
            messages.warning(request, 'Email not valid or already in use')
            return redirect('profile-settings')
        
    return redirect('profile-settings')


@login_required
def profile_usernamechange(request):
    """
    Handle username changes.
    
    This function operates in two modes:
    1. HTMX request: Returns just the username form (for dynamic loading)
    2. POST request: Processes username change submission
    
    During username change:
    - Validates the new username
    - Checks for duplicates (via form validation)
    - Updates the username
    - Shows success/error message
    
    """
    if request.htmx:
        form = UsernameForm(instance=request.user)
        return render(request, 'partials/username_form.html', {'form':form})
    
    if request.method == 'POST':
        form = UsernameForm(request.POST, instance=request.user)
        
        if form.is_valid():
            form.save()
            messages.success(request, 'Username updated successfully.')
            return redirect('profile-settings')
        else:
            messages.warning(request, 'Username not valid or already in use')
            return redirect('profile-settings')
    
    return redirect('profile-settings')    


@login_required
def profile_emailverify(request):
    """
    Send email verification link.
    
    This simple function triggers the sending of a verification email
    to the user's current email address.
    
    Parameters:
        request: The HTTP request object
        
    """
    send_email_confirmation(request, request.user)
    return redirect('profile-settings')


@login_required
def profile_delete_view(request):
    """
    Handle account deletion.
    
    This function:
    1. Displays confirmation page for account deletion on GET
    2. Processes account deletion on POST:
       - Logs the user out
       - Deletes the user account
       - Shows confirmation message
       - Redirects to home page

    """
    user = request.user
    if request.method == "POST":
        logout(request)
        user.delete()
        messages.success(request, 'Account deleted, what a pity')
        return redirect('home')
    
    return render(request, 'a_users/profile_delete.html')
