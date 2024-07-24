from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from flask_wtf.csrf import CSRFProtect
import time
import bleach
import base64
from PIL import Image
import io, re

# Initialize Flask app, CSRF protection, and SocketIO
app = Flask(__name__)
app.config['SECRET_KEY'] = 'W0rmyOn@St1ck'
csrf = CSRFProtect(app)
socketio = SocketIO(app, cors_allowed_origins="*", ping_interval=10, ping_timeout=60*2)

# Dictionaries for tracking sessions, usernames, and cooldowns
session_message_times = {}
session_usernames = {}
session_cooldowns = {}
connected_users = {}
active_usernames = set()
session_join_times = {}
last_username_change = {}
active_tabs = {}
last_image_upload = {}  # Dictionary to track last image upload time
#todo fibonarci sequence
unique_sessions = {}
# Constants for message handling
MESSAGE_THRESHOLD = 6
MESSAGE_DELAY = 10  # milliseconds
COOLDOWN_PERIOD = 5  # seconds
SPAM_BAN_PERIOD = 5  # seconds
HACK_BAN_PERIOD = 5 * 60  # seconds
JOIN_THRESHOLD = 7  # Number of joins within the period to trigger ban
JOIN_PERIOD = 10  # Period in seconds to check for join frequency
USERNAME_CHANGE_PERIOD = 30 * 60  # 30 minutes in seconds
IMAGE_UPLOAD_COOLDOWN = 5 * 60  # 5 minutes in seconds

# Global list to store past messages and images in order
past_messages = []


# list of word replacements, words-to-replace are seperated by " / "
# not case sensitive
naughtyWords = {
    "balderdash": "fuk / phuck",
    "bindlestiff": "clitoris",
    "bologne": "basterd",
    "bosom": "boobs / tits / titty",
    "bosoms": "boobies / titties",
    "breeches": "muff / nutsack / scrotum",
    "bumfuzzle": "dumbass",
    "carbuncle": "jackass",
    "cheese and crackers": "motherf*cker, motherf*cking",
    "child born out of wedlock": "bastard",
    "codswallop": "douche / douchebag",
    "curmudgeon": "boner",
    "dagnabbit": "cocksucker / sh*t, sht / fcuk",
    "doodle": "cock / dick / penis",
    "escort": "whore",
    "fellmonger": "prick / wank",
    "flummery": "cum / semen / shit",
    "fopdoodle": "Hitier / Hitler / Moonman / M o o n m a n / Stalin",
    "fusty": "jizz",
    "gardyloo": "orgasm / thatass",
    "gee golly": "damn / damnit",
    "hard worker": "slave",
    "harlot": "dyke / kunt[Note 1] / nympho / skank / slut / tramp / twat / whore",
    "kick the bucket": "kys / kill yourself",
    "kitty": "pussy",
    "lord almighty": "Allah Ackbar",
    "malarky": "queef / porn",
    "mumblecrusted": "fisted",
    "mumblecrusting": "fisting",
    "nonbinary": "homo / transexual",
    "petticoat": "dildo",
    "pillion": "anal / anus / ass / asshole",
    "pillions": "asses",
    "plague": "herpes / hiv / std",
    "plant a flower": "suck it / suck me off",
    "premarital relations": "blowjob / fellatio / handjob / rimjob",
    "prithee transport thyself to tarnation": "go to hell",
    "pumpkin pie": "creampie",
    "raggabrash": "kkk",
    "rascal": "scumbag",
    "rigamole": "bukkake",
    "rose": "vagina",
    "rosebud": "clit",
    "savant": "autistic / retarded",
    "snap crackle pop": "bitch / b*tch / biatch",
    "something": "blow job",
    "son of a gun": "bullshit",
    "tell me more": "stfu",
    "tarnation": "fuck / fucked / fucker / fucking",
    "townie": "nazi",
    "yaldson": "anilingus",
    "you are a great player": "you suck",
    "you are an amazing player": "you are garbage / you're garbage / you are trash / you're trash",
    "you are an upstanding citizen": "you are gay / you're gay",
    "zounderkite": "retard",
    }

# Validate the username
def validate_username(username):
    return bool(username) and len(username) <= 30

# Replaces instances of naughty words with alternatives based on the given dictionary 
def filter_message(message):
    cleanMessage = message
    for word in naughtyWords:
        badwords = naughtyWords[word]

        for badword in badwords.split(" / "):

            replacement_word = word
            bad_word = badword.lower()

            cleanMessage = re.sub(r"( |\b)"+bad_word+r"( |\b)", " "+replacement_word+" ", cleanMessage)

    return cleanMessage

# Validate the message
def validate_message(message):    
    return bool(message) and len(message) <= 400

# Sanitize input text to prevent script injection
def sanitize_input(text):
    return bleach.clean(text, tags=set([]))

def resize_image(image_data):
    image = Image.open(io.BytesIO(base64.b64decode(image_data.split(",")[1])))
    image = image.resize((200, 200))
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    resized_image_data = base64.b64encode(buffered.getvalue()).decode('utf-8')
    return f"data:image/png;base64,{resized_image_data}"

@app.route('/skibchat')
def chat():
    # Render the chat interface with past messages and images
    return render_template('chat.html', past_messages=past_messages)

@socketio.on('message')
def handle_message(data):
    # Handle incoming messages from clients
    username = sanitize_input(data.get('username', ''))
    message = sanitize_input(data.get('text', ''))
    ip_id = request.environ.get('REMOTE_ADDR')+":"+str(request.environ.get('REMOTE_PORT'))
    
    message = filter_message(message)


    if validate_username(username) and validate_message(message):
        current_time = time.time()
        
        # Check for session cooldown
        if ip_id in session_cooldowns and current_time < session_cooldowns[ip_id]:
            remaining_time = int(session_cooldowns[ip_id] - current_time)
            emit('error', {'message': f"Please wait {remaining_time} seconds before sending more messages."}, broadcast=False)
            return

        if ip_id not in session_message_times:
            session_message_times[ip_id] = []
        if ip_id not in session_usernames:
            session_usernames[ip_id] = set()
        
        session_usernames[ip_id].add(username.lower())
        
        # Check for rapid username changes
        if len(session_usernames[ip_id]) > MESSAGE_THRESHOLD:
            session_usernames[ip_id].clear()
            session_cooldowns[ip_id] = current_time + HACK_BAN_PERIOD
            emit('error', {'message': f"Please don't change usernames rapidly, you have been put on a {HACK_BAN_PERIOD // 60} minute ban."}, broadcast=False)
            emit('message', {'username': '', 'text': f'{username} has been banned for {HACK_BAN_PERIOD // 60} minutes for hacking.', 'color': '#d16262'}, broadcast=True)
            return

        # Append the current message time
        session_message_times[ip_id].append(current_time)
        if len(session_message_times[ip_id]) > MESSAGE_THRESHOLD:
            session_message_times[ip_id] = session_message_times[ip_id][-MESSAGE_THRESHOLD:]

        # Check for spamming
        if len(session_message_times[ip_id]) == MESSAGE_THRESHOLD and (session_message_times[ip_id][-1] - session_message_times[ip_id][0] < MESSAGE_DELAY):
            session_message_times[ip_id] = []
            session_cooldowns[ip_id] = current_time + SPAM_BAN_PERIOD
            emit('error', {'message': f"Please don't spam, you have been put on a {SPAM_BAN_PERIOD} second ban."}, broadcast=False)
            emit('message', {'username': '', 'text': f'{username} has been banned for {SPAM_BAN_PERIOD} seconds for spamming.', 'color': '#d16262'}, broadcast=True)
        else:
            # Append message to global past_messages list
            past_messages.append({'type': 'message', 'username': username, 'text': message, 'timestamp': current_time})
            if len(past_messages) > 30:
                past_messages.pop(0)
            emit('message', {'type': 'message', 'username': username, 'text': message}, broadcast=True)
    else:
        emit('error', {'message': 'Please stay below 400 characters.'}, broadcast=False)

@socketio.on('join')
def handle_join(data):
    # Handle new users joining the chat
    username = sanitize_input(data.get('username', ''))
    ip_id = request.environ.get('REMOTE_ADDR')+":"+str(request.environ.get('REMOTE_PORT'))
    username_lower = username.lower()
    # current_time = time.time()

    if validate_username(username):
        if ip_id not in connected_users:
            connected_users[ip_id] = username
            active_usernames.add(username_lower)
            active_tabs[ip_id] = 1

            join_message = f'{username} has joined the chat'
            emit('user joined', {'message': join_message}, broadcast=True)

        emit('update user count', {'count': len(active_usernames)}, broadcast=True)
        emit('update online users', {'users': list(active_usernames)}, broadcast=True)
    else:
        emit('error', {'message': 'Invalid username'}, broadcast=False)

@socketio.on('focus')
def handle_focus(data):
    username = sanitize_input(data.get('username', ''))
    username_lower = username.lower()

    if validate_username(username):
        if username_lower not in active_usernames:
            active_usernames.add(username_lower)
            emit('update user count', {'count': len(active_usernames)}, broadcast=True)
            emit('update online users', {'users': list(active_usernames)}, broadcast=True)

@socketio.on('blur')
def handle_blur(data):
    username = sanitize_input(data.get('username', ''))
    username_lower = username.lower()

    if validate_username(username):
        if username_lower in active_usernames:
            active_usernames.remove(username_lower)
            emit('update user count', {'count': len(active_usernames)}, broadcast=True)
            emit('update online users', {'users': list(active_usernames)}, broadcast=True)

@socketio.on('change_username')
def handle_change_username(data):
    # Handle username changes
    old_username = sanitize_input(data.get('old_username', ''))
    new_username = sanitize_input(data.get('new_username', ''))
    ip_id = request.environ.get('REMOTE_ADDR')+":"+str(request.environ.get('REMOTE_PORT'))
    new_username_lower = new_username.lower()

    if validate_username(new_username):
        if new_username_lower in active_usernames:
            emit('error', {'message': 'Username already taken'}, broadcast=False)
        else:
            # Remove old username and add new username
            active_usernames.discard(old_username.lower())
            active_usernames.add(new_username_lower)
            connected_users[ip_id] = new_username

            # Emit username change message
            emit('username_changed', {'old_username': old_username, 'new_username': new_username}, broadcast=True)
            
            # Update user count without emitting join message again
            emit('update user count', {'count': len(active_usernames)}, broadcast=True)
            emit('update online users', {'users': list(active_usernames)}, broadcast=True)
    else:
        emit('error', {'message': 'Invalid username'}, broadcast=False)

@socketio.on('disconnect')
def handle_disconnect():
    # Handle user disconnection
    session_id = request.cookies.get('session_id')
    ip_id = request.environ.get('REMOTE_ADDR')+":"+str(request.environ.get('REMOTE_PORT'))
    if ip_id in active_tabs:
        active_tabs[ip_id] -= 1
        if active_tabs[ip_id] == 0:
            username = connected_users.pop(ip_id, None)
            if username and username.lower() in active_usernames:
                active_usernames.remove(username.lower())
                emit('update user count', {'count': len(active_usernames)}, broadcast=True)
                emit('update online users', {'users': list(active_usernames)}, broadcast=True)

@socketio.on('image')
def handle_image(data):
    username = sanitize_input(data.get('username', ''))
    image_data = data.get('image')
    ip_id = request.environ.get('REMOTE_ADDR')+":"+str(request.environ.get('REMOTE_PORT'))
    current_time = time.time()

    if validate_username(username) and image_data:
        # Check if the user has uploaded an image within the last 5 minutes
        if ip_id in last_image_upload and (current_time - last_image_upload[ip_id] < IMAGE_UPLOAD_COOLDOWN):
            remaining_time = int(IMAGE_UPLOAD_COOLDOWN - (current_time - last_image_upload[ip_id]))
            minutes, seconds = divmod(remaining_time, 60)
            emit('error', {'message': f"Please wait {minutes}:{seconds:02d} before uploading another image."}, broadcast=False)
        else:
            last_image_upload[ip_id] = current_time
            resized_image_data = resize_image(image_data)
            # Append image to global past_messages list
            past_messages.append({'type': 'image', 'username': username, 'image': resized_image_data, 'timestamp': current_time})
            if len(past_messages) > 30:
                past_messages.pop(0)
            emit('image', {'type': 'image', 'username': username, 'image': resized_image_data}, broadcast=True)
    else:
        emit('error', {'message': 'Invalid input or missing image data'}, broadcast=False)

@socketio.on('clean')
def handle_clean(data):
    # Send all past messages to the client who requested the clean action
    for msg in past_messages:
        if msg['type'] == 'message':
            emit('message', {'type': 'message', 'username': msg['username'], 'text': msg['text']}, broadcast=False)
        elif msg['type'] == 'image':
            emit('image', {'type': 'image', 'username': msg['username'], 'image': msg['image']}, broadcast=False)

if __name__ == '__main__':
    socketio.run(app, debug=True)
