from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from a_rtchat.models import ChatGroup
from django.contrib import messages
from .forms import * 
from django.contrib.auth.models import User
from django.views.decorators.http import require_http_methods
# Create your views here.


@login_required
def chat_view(request, chatroom_name='public-chat'):
    """
    Display the chat interface for a specific chatroom.
    
    This function handles three types of chat rooms:
    1. Public chat - accessible to everyone without verification
    2. Private direct messages - only accessible to the two participants
    3. Group chats - requires email verification to join

    """

    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    # Get the last 40 messages for the chatroom
    chat_messages = chat_group.chat_messages.all()[:40]
    form = ChatmessageCreateForm()

    other_user = None
    
    # 1. Public chat - accessible to everyone
    if chatroom_name == 'public-chat':
        # Ensure user is a member (no verification needed)
        if request.user not in chat_group.members.all():
            chat_group.members.add(request.user)
    
    # 2. Private chat (direct messages)
    elif chat_group.is_private:
        # Ensure user is a member (no verification needed)
        if request.user not in chat_group.members.all():
            raise Http404()
        # Get the other user in the private chat
        for member in chat_group.members.all():
            if member != request.user:
                other_user = member
                break
                
    # 3. Group chats - need verification
    else:
        # Check email verification
        if not request.user.emailaddress_set.filter(verified=True).exists():
            messages.warning(request, 'Please verify your email address to join this group chat.')
            return redirect('profile-settings')
            
        # Add to members if verified
        if request.user not in chat_group.members.all():
            chat_group.members.add(request.user)
    
    # Process new messages submitted via HTMX
    if request.htmx:
        form = ChatmessageCreateForm(request.POST)
        if form.is_valid():
            message = form.save(commit=False)
            message.author = request.user
            message.group = chat_group
            message.save()
            context = {
                'message':message,
                'user' : request.user
            }
            return render(request , 'a_rtchat/partials/chat_message_p.html', context)

    context = {
        'chatroom_name': chatroom_name,
        'chat_messages': chat_messages,
        'form': form,
        'other_user': other_user,
        'chat_group' : chat_group,
    }

    return render(request, 'a_rtchat/chat.html', context )


@login_required
def get_or_create_chatroom(request, username):
    """
    Get an existing private chat with a user or create a new one.
    
    This function finds or creates a private chatroom between the current
    user and another user specified by username.
    
    """
    if request.user.username == username:
        return redirect('home')
    
    # Check if the user exists
    other_user = User.objects.get(username=username)
    my_chatrooms = request.user.chat_groups.filter(is_private=True)

    if my_chatrooms.exists():
        for chatroom in my_chatrooms:
            # Check if the other user is a member of the chatroom
            if other_user in chatroom.members.all():
                chatroom = chatroom
                break
            else:
                # Create a new private chatroom if the other user is not a member
                chatroom = ChatGroup.objects.create(is_private=True)
                chatroom.members.add(other_user,request.user )
    else:
        chatroom = ChatGroup.objects.create(is_private=True)
        chatroom.members.add(other_user,request.user )
    return redirect('chatroom', chatroom.group_name)


@login_required
def create_groupchat(request):
    """
    Create a new group chat.
    
    Displays the form to create a new group chat and processes
    form submission. The current user becomes the admin of the new group.
    
    """
    form = NewGroupForm()
    if request.method == 'POST':
        form = NewGroupForm(request.POST)
        if form.is_valid():
            new_groupchat = form.save(commit=False)
            new_groupchat.admin = request.user
            new_groupchat.save()
            new_groupchat.members.add(request.user)
            return redirect('chatroom', new_groupchat.group_name)
    context = {
        'form': form,
    }
    return render(request, 'a_rtchat/create_groupchat.html', context)


@login_required
def chatroom_edit_view(request, chatroom_name):
    """
    Edit chatroom settings and manage members.
    
    Only the admin of the chatroom can access this view. Allows changing 
    chatroom settings and removing members. When members are removed,
    WebSocket notifications are sent to them.
    
    """
    # Check if the user is the admin of the chatroom
    # If not, raise a 404 error
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    if request.user != chat_group.admin:
        raise Http404()
    
    form = ChatRoomEditForm(instance=chat_group)

    if request.method == 'POST':
        form = ChatRoomEditForm(request.POST, instance=chat_group)
        if form.is_valid():
            form.save()

            # Get removed members before removing them
            removed_members = []
            remove_members = request.POST.getlist('remove_members')
            
            for member_id in remove_members:
                member = User.objects.get(id=member_id)
                removed_members.append(member)
                chat_group.members.remove(member)
            
            # Send WebSocket notifications to removed members
            if removed_members:
                from channels.layers import get_channel_layer
                from asgiref.sync import async_to_sync
                
                channel_layer = get_channel_layer()
                for member in removed_members:
                    # Send message to notify the member they've been removed
                    # This will trigger a WebSocket event that redirects them to home
                    async_to_sync(channel_layer.group_send)(
                        chatroom_name,
                        {
                            'type': 'member_removed',
                            'removed_user_id': member.id
                        }
                    )
            
            return redirect('chatroom', chatroom_name)

    context = {
        'form': form,
        'chat_group': chat_group,
    }
    return render(request, 'a_rtchat/chatroom_edit.html', context)


@login_required
def chatroom_delete_view(request, chatroom_name):
    """
    Delete a chatroom.
    
    Only the admin of the chatroom can delete it. Displays a confirmation
    page and handles the actual deletion when confirmed.
    
    """
    # Check if the user is the admin of the chatroom
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name) 
    if request.user != chat_group.admin:
        raise Http404()
    if request.method == 'POST':
        chat_group.delete()
        messages.success(request, 'Chatroom deleted successfully.')
        return redirect('home')
    return render(request,'a_rtchat/chatroom_delete.html',{'chat_group': chat_group})


@login_required
def chatroom_leave_view(request,chatroom_name):
    """
    Leave a chatroom.
    
    Allows a user to leave a chatroom they are a member of.
    Removes the user from the members list and redirects to home.
    
    """
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    if request.user not in chat_group.members.all():
        raise Http404()
    if request.method == 'POST':
        chat_group.members.remove(request.user)
        messages.success(request, 'You have left the chatroom.')
        return redirect('home')