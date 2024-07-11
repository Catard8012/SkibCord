from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from flask_wtf.csrf import CSRFProtect
import time
import bleach
import uuid
import base64
from PIL import Image
import io
from datetime import datetime

# Initialize Flask app, CSRF protection, and SocketIO
app = Flask(__name__)
app.config['SECRET_KEY'] = 'W0rmyOn@St1ck'
csrf = CSRFProtect(app)
socketio = SocketIO(app, cors_allowed_origins="*", ping_interval=10, ping_timeout=60*2, transport="websocket")

# Dictionaries for tracking sessions, usernames, and cooldowns
session_message_times = {}
session_usernames = {}
session_cooldowns = {}
connected_users = {}
active_usernames = set()
unique_sessions = {}
session_join_times = {}
last_username_change = {}
active_tabs = {}
last_image_upload = {}  # Dictionary to track last image upload time

# Constants for message handling
MESSAGE_THRESHOLD = 7
MESSAGE_DELAY = 10  # milliseconds
COOLDOWN_PERIOD = 5  # seconds
SPAM_BAN_PERIOD = 5  # seconds
HACK_BAN_PERIOD = 5 * 60  # seconds
JOIN_THRESHOLD = 7  # Number of joins within the period to trigger ban
JOIN_PERIOD = 10  # Period in seconds to check for join frequency
USERNAME_CHANGE_PERIOD = 30 * 60  # 30 minutes in seconds
IMAGE_UPLOAD_COOLDOWN = 5 * 60  # 5 minutes in seconds

# Validate the username
def validate_username(username):
    return bool(username) and len(username) <= 30

# Validate the message
def validate_message(message):
    return bool(message) and len(message) <= 400

# Sanitize input text to prevent script injection
def sanitize_input(text):
    return bleach.clean(text, tags=[])

def resize_image(image_data):
    image = Image.open(io.BytesIO(base64.b64decode(image_data.split(",")[1])))
    image = image.resize((200, 200))
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    resized_image_data = base64.b64encode(buffered.getvalue()).decode('utf-8')
    return f"data:image/png;base64,{resized_image_data}"

@app.route('/skibchat')
def chat():
    # Render the chat interface
    return render_template('chat.html')

@socketio.on('message')
def handle_message(data):
    # Handle incoming messages from clients
    username = sanitize_input(data.get('username', ''))
    message = sanitize_input(data.get('text', ''))
    session_id = data.get('session_id')

    if validate_username(username) and validate_message(message):
        current_time = time.time()
        
        # Check for session cooldown
        if session_id in session_cooldowns and current_time < session_cooldowns[session_id]:
            remaining_time = int(session_cooldowns[session_id] - current_time)
            emit('error', {'message': f"Please wait {remaining_time} seconds before sending more messages."}, broadcast=False)
            return

        if session_id not in session_message_times:
            session_message_times[session_id] = []
        if session_id not in session_usernames:
            session_usernames[session_id] = set()
        
        session_usernames[session_id].add(username.lower())
        
        # Check for rapid username changes
        if len(session_usernames[session_id]) > MESSAGE_THRESHOLD:
            session_usernames[session_id].clear()
            session_cooldowns[session_id] = current_time + HACK_BAN_PERIOD
            emit('error', {'message': f"Please don't change usernames rapidly, you have been put on a {HACK_BAN_PERIOD // 60} minute ban."}, broadcast=False)
            emit('message', {'username': '', 'text': f'{username} has been banned for {HACK_BAN_PERIOD // 60} minutes for hacking.', 'color': '#d16262'}, broadcast=True)
            return

        # Append the current message time
        session_message_times[session_id].append(current_time)
        if len(session_message_times[session_id]) > MESSAGE_THRESHOLD:
            session_message_times[session_id] = session_message_times[session_id][-MESSAGE_THRESHOLD:]

        # Check for spamming
        if len(session_message_times[session_id]) == MESSAGE_THRESHOLD and (session_message_times[session_id][-1] - session_message_times[session_id][0] < MESSAGE_DELAY):
            session_message_times[session_id] = []
            session_cooldowns[session_id] = current_time + SPAM_BAN_PERIOD
            emit('error', {'message': "Please don't spam, you have been put on a 5 second ban."}, broadcast=False)
            emit('message', {'username': '', 'text': f'{username} has been banned for {SPAM_BAN_PERIOD} seconds for spamming.', 'color': '#d16262'}, broadcast=True)
        else:
            emit('message', {'username': username, 'text': message}, broadcast=True)
    else:
        emit('error', {'message': 'Please stay below 400 characters.'}, broadcast=False)

@socketio.on('join')
def handle_join(data):
    # Handle new users joining the chat
    username = sanitize_input(data.get('username', ''))
    session_id = data.get('session_id')
    username_lower = username.lower()
    # current_time = time.time()

    if validate_username(username):
        if session_id not in connected_users:
            connected_users[session_id] = username
            active_usernames.add(username_lower)
            active_tabs[session_id] = 1

            join_message = f'{username} has joined the chat'
            emit('user joined', {'message': join_message}, broadcast=True)
        else:
            active_tabs[session_id] += 1

        emit('update user count', {'count': len(active_usernames)}, broadcast=True)
        emit('update online users', {'users': list(active_usernames)}, broadcast=True)
    else:
        emit('error', {'message': 'Invalid username'}, broadcast=False)

@socketio.on('change_username')
def handle_change_username(data):
    # Handle username changes
    old_username = sanitize_input(data.get('old_username', ''))
    new_username = sanitize_input(data.get('new_username', ''))
    session_id = data.get('session_id')
    new_username_lower = new_username.lower()
    current_time = time.time()

    if validate_username(new_username):
        # Check if enough time has passed since the last username change
        if session_id in last_username_change and (current_time - last_username_change[session_id] < USERNAME_CHANGE_PERIOD):
            next_change_time = datetime.fromtimestamp(last_username_change[session_id] + USERNAME_CHANGE_PERIOD)
            next_change_time_str = next_change_time.strftime('%I:%M %p').lstrip('0')
            emit('error', {'message': f"You can change your username again at {next_change_time_str}."}, broadcast=False)
            return

        if new_username_lower in active_usernames:
            emit('error', {'message': 'Username already taken'}, broadcast=False)
        else:
            # Remove old username and add new username
            active_usernames.remove(old_username.lower())
            active_usernames.add(new_username_lower)
            connected_users[session_id] = new_username

            # Emit username change message
            emit('username_changed', {'old_username': old_username, 'new_username': new_username}, broadcast=True)
            
            # Update the last username change time
            last_username_change[session_id] = current_time
            
            # Update user count without emitting join message again
            emit('update user count', {'count': len(active_usernames)}, broadcast=True)
            emit('update online users', {'users': list(active_usernames)}, broadcast=True)
    else:
        emit('error', {'message': 'Invalid username'}, broadcast=False)

@socketio.on('disconnect')
def handle_disconnect():
    # Handle user disconnection
    session_id = request.cookies.get('session_id')
    if session_id in active_tabs:
        active_tabs[session_id] -= 1
        if active_tabs[session_id] == 0:
            username = connected_users.pop(session_id, None)
            if username and username.lower() in active_usernames:
                active_usernames.remove(username.lower())
                leave_message = f'{username} has left the chat'
                emit('user left', {'message': leave_message}, broadcast=True)
                emit('update user count', {'count': len(active_usernames)}, broadcast=True)
                emit('update online users', {'users': list(active_usernames)}, broadcast=True)

@socketio.on('image')
def handle_image(data):
    username = sanitize_input(data.get('username', ''))
    image_data = data.get('image')
    session_id = data.get('session_id')
    current_time = time.time()

    if validate_username(username) and image_data:
        # Check if the user has uploaded an image within the last 5 minutes
        if session_id in last_image_upload and (current_time - last_image_upload[session_id] < IMAGE_UPLOAD_COOLDOWN):
            remaining_time = int(IMAGE_UPLOAD_COOLDOWN - (current_time - last_image_upload[session_id]))
            minutes, seconds = divmod(remaining_time, 60)
            emit('error', {'message': f"Please wait {minutes}:{seconds:02d} before uploading another image."}, broadcast=False)
        else:
            last_image_upload[session_id] = current_time
            resized_image_data = resize_image(image_data)
            emit('image', {'username': username, 'image': resized_image_data}, broadcast=True)
    else:
        emit('error', {'message': 'Invalid input or missing image data'}, broadcast=False)

if __name__ == '__main__':
    socketio.run(app, debug=True)
