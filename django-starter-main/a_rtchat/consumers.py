import json
from channels.generic.websocket import WebsocketConsumer
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from asgiref.sync import async_to_sync
from a_rtchat.models import ChatGroup, GroupMessage
from django.contrib.auth.models import User

class ChatroomConsumer(WebsocketConsumer):
  """
  WebSocket consumer class for handling real-time chat functionality.
  
  This consumer manages WebSocket connections to chat rooms, handles message 
  sending/receiving, tracks online users, and manages security permissions.
  """
  
  def connect(self):
    """
    Establish WebSocket connection with permission checks.
    
    This method:
    1. Verifies user authentication
    2. Enforces access control based on chat room type:
       - Public chat: Open to all authenticated users
       - Private chat: Only accessible to chat members
       - Group chat: Requires email verification and membership
    3. Adds user to the channel group for message broadcasting
    4. Adds user to the online users list
    5. Updates the online count for all users in the room
    
    Returns:
        None. Accepts or closes the connection based on permissions.
    """
    self.user = self.scope['user']
    # First check if user is authenticated
    if self.user.is_anonymous:
        self.close()
        return
    
    # Get real User object (not lazy)
    self.user = User.objects.get(pk=self.user.id)
    
    self.chatroom_name = self.scope['url_route']['kwargs']['chatroom_name'] 
    self.chatroom = get_object_or_404(ChatGroup, group_name=self.chatroom_name)
    
    # 1. Public chat - accessible to everyone
    if self.chatroom_name == 'public-chat':
        # No verification needed
        pass
        
    # 2. Private chat (direct messages)
    elif self.chatroom.is_private:
        if self.user not in self.chatroom.members.all():
            self.close()
            return
            
    # 3. Group chats - need verification
    else:
        # Check if user is verified
        if not self.user.emailaddress_set.filter(verified=True).exists():
            self.close()
            return
            
        # Check if user is a member
        if self.user not in self.chatroom.members.all():
            self.close()
            return
            
    # If we reach here, the user is allowed in the chat
    async_to_sync(self.channel_layer.group_add)(
        self.chatroom_name,
        self.channel_name
    )

    # Add user to online users
    if self.user not in self.chatroom.users_online.all():
        self.chatroom.users_online.add(self.user)
        self.update_online_count()

    self.accept()

  def disconnect(self, close_code):
    """
    Handle WebSocket disconnection.
    
    This method:
    1. Removes the user from the channel group
    2. Removes the user from the online users list
    3. Updates the online count for all remaining users
    
    Parameters:
        close_code: WebSocket close code
        
    Returns:
        None
    """
    async_to_sync(self.channel_layer.group_discard)(
      self.chatroom_name,
      self.channel_name
    )
    if self.user in self.chatroom.users_online.all():
      self.chatroom.users_online.remove(self.user)
      self.update_online_count()

  def receive(self, text_data):
    """
    Process incoming WebSocket messages (new chat messages).
    
    This method:
    1. Parses the JSON message data
    2. Creates a new GroupMessage in the database
    3. Triggers a message event to broadcast to all users in the chat
    
    Parameters:
        text_data: JSON string containing the message body
        
    Returns:
        None. Triggers message_handler for all users.
    """
    text_data_json = json.loads(text_data)
    body = text_data_json['body']
    
    message = GroupMessage.objects.create(
      author=self.user,
      group=self.chatroom,
      body=body
    )
    
    # Create an event to broadcast to the group
    event = {
      'type': 'message_handler',  # This must match the method name without "_handler"
      'message_id': message.id,
    }

    async_to_sync(self.channel_layer.group_send)( 
      self.chatroom_name, event
    )

  def message_handler(self, event):
    """
    Handle chat message events and send to the client.
    
    This method:
    1. Gets the message from the database using the message_id
    2. Renders the message HTML using a template
    3. Sends the rendered HTML to the WebSocket client
    
    Parameters:
        event: Dict containing message_id
        
    Returns:
        None. Sends HTML to the WebSocket client.
    """
    message_id = event['message_id']
    message = GroupMessage.objects.get(id=message_id)
    
    context = {
        'message': message,
        'user': self.user  # Must be included for proper message rendering
    }
    
    html = render_to_string('a_rtchat/partials/chat_message_p.html', context)
    self.send(text_data=html)

  def update_online_count(self):
    """
    Update and broadcast the count of online users.
    
    This method:
    1. Counts users currently online in the chatroom
    2. Creates an event with the updated count
    3. Broadcasts the event to all users in the chatroom
    
    Returns:
        None. Triggers online_count_handler for all users.
    """
    # Count how many users are currently online
    online_count = self.chatroom.users_online.count()

    event = {
      'type': 'online_count_handler',
      'online_count': online_count
    }
    # Send to everyone in the chatroom
    async_to_sync(self.channel_layer.group_send)(self.chatroom_name, event)

  def online_count_handler(self, event):
    """
    Handle online count update events and send to the client.
    
    This method:
    1. Gets the online count from the event
    2. Renders the online count HTML using a template
    3. Sends the rendered HTML to the WebSocket client
    
    Parameters:
        event: Dict containing online_count
        
    Returns:
        None. Sends HTML to the WebSocket client.
    """
    online_count = event['online_count']
    
    context = {
      'online_count': online_count,
      'chat_group': self.chatroom,
    }
    html = render_to_string('a_rtchat/partials/online_count.html', context)
    self.send(text_data=html)

  def member_removed(self, event):
    """
    Handle member removal events from the chatroom.
    
    This method:
    1. Checks if the current user is the one being removed
    2. If so, sends a JSON message to the client to redirect to home page
    3. The client-side JavaScript will handle the actual redirection
    
    This is triggered when an admin removes a user from a chatroom.
    
    Parameters:
        event: Dict containing removed_user_id
        
    Returns:
        None. May send redirect instruction to client.
    """
    removed_user_id = event['removed_user_id']
    
    # Check if the current user is the removed one
    if self.user.id == removed_user_id:
        # Send a message to redirect the user
        self.send(text_data=json.dumps({
            'type': 'redirect',
            'url': '/'  # Redirect to home page
        }))