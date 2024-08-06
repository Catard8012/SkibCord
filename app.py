from flask import Flask, render_template, request, make_response
from flask_socketio import SocketIO, emit
from flask_wtf.csrf import CSRFProtect
import time
import bleach
import base64
from PIL import Image, ImageSequence, ImageOps
import io, re
from datetime import datetime, timedelta
import random
import uuid

# Initialize Flask app, CSRF protection, and SocketIO
app = Flask(__name__)
app.config['SECRET_KEY'] = 'W0rmyOn@St1ck'
csrf = CSRFProtect(app)
socketio = SocketIO(app, cors_allowed_origins="*", ping_interval=10, ping_timeout=60*2)

# Australian Eastern Standard Time (AEST) offset
AEST_OFFSET = 10  # UTC+10

# Dictionaries for tracking sessions, usernames, and cooldowns
session_message_times = {}
session_usernames = {}
session_cooldowns = {}
connected_users = {}
active_usernames = set()
session_join_times = {}
active_tabs = {}
last_image_upload = {}  # Dictionary to track last image upload time
profile_pictures = {}  # Dictionary to store user profile pictures
last_message = {'session_id': None, 'timestamp': 0}  # Track the session ID and timestamp of the last message

# Constants for message handling
MESSAGE_THRESHOLD = 6
MESSAGE_DELAY = 10  # milliseconds
COOLDOWN_PERIOD = 5  # seconds
SPAM_BAN_PERIOD = 5  # seconds
HACK_BAN_PERIOD = 5 * 60  # seconds
JOIN_THRESHOLD = 7  # Number of joins within the period to trigger ban
JOIN_PERIOD = 10  # Period in seconds to check for join frequency
USERNAME_CHANGE_PERIOD = 60  # 1 minute in seconds
IMAGE_UPLOAD_COOLDOWN = 60  # 1 minute in seconds
PROFILE_PIC_SIZE = (50, 50)  # Size of the profile picture
MAX_IMAGE_SIZE = (1024, 1024)  # Max size for uploaded images
GROUP_MESSAGE_TIME = 3 * 60  # 3 minutes in seconds

# Global list to store past messages and images in order
past_messages = []

# List of word replacements, words-to-replace are separated by " / "
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
    "bike": "kike",
    "gardyloo": "orgasm / thatass",
    "gee golly": "damn / damnit",
    "hard worker": "slave",
    "cutie": "cunt",
    "nincompoop": "nigger / nigga / negro / negroe / jiggerboo / jiggaboo / coon", 
    "nincompoops": "niggers / niggas / negros / negroes / jiggerboos / jiggaboos / coons", 
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

# List of default profile images
default_images = [
    'static/Images/Skibcord-blue.png',
    'static/Images/Skibcord-green.png',
    'static/Images/Skibcord-red.png',
    'static/Images/Skibcordlogo-CS1.png',
    'static/Images/Skibcordlogo-CS2.png',
    'static/Images/Skibcord-yellow.png'
]

def get_random_profile_image():
    return random.choice(default_images)

# Validate the username
def validate_username(username):
    return bool(username) and len(username) <= 30 and username.lower() != 'skibbot'

# Validate the message
def validate_message(message):
    return bool(message) and len(message) <= 400

# Censor naughty words in the message
def censor_message(message):
    for replacement, words in naughtyWords.items():
        for word in words.split(" / "):
            pattern = re.compile(re.escape(word), re.IGNORECASE)
            message = pattern.sub(replacement, message)
    return message

# Sanitize input text to prevent script injection
def sanitize_input(text):
    return bleach.clean(text, tags=set([]))

# Function to resize an image, handling GIFs to retain animation
def resize_image(image_data):
    image = Image.open(io.BytesIO(base64.b64decode(image_data.split(",")[1])))
    if image.format == 'GIF':
        return image_data  # Skip resizing for GIFs to keep animations

    ratio = image.width / image.height
    width = int(200 * ratio)  # Calculate width while maintaining aspect ratio
    height = 200  # Fixed height

    image = image.resize((width, height))
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")

    resized_image_data = base64.b64encode(buffered.getvalue()).decode('utf-8')
    return f"data:image/png;base64,{resized_image_data}"

def format_datetime(timestamp):
    now = datetime.utcnow() + timedelta(hours=AEST_OFFSET)
    dt = datetime.utcfromtimestamp(timestamp) + timedelta(hours=AEST_OFFSET)
    
    if dt.date() == now.date():
        return f"Today at {dt.strftime('%I:%M%p').lower()}"
    elif dt.date() == (now.date() - timedelta(days=1)):
        return f"Yesterday at {dt.strftime('%I:%M%p').lower()}"
    else:
        return dt.strftime('%d/%m/%Y %I:%M%p').lower()

# Ensure messages from different users are not grouped
def should_group_message(last_message, current_session, current_time):
    return last_message['session_id'] == current_session and (current_time - last_message['timestamp']) < GROUP_MESSAGE_TIME

@app.route('/')
def fake():
    return "This site is under construction. We plan to add maths articles intended for school students."
    
@app.route('/skibchat')
def chat():
    session_id = request.cookies.get('session_id')
    if not session_id:
        session_id = str(uuid.uuid4())
        response = make_response(render_template('chat.html', past_messages=past_messages, bot_name='SkibBot', bot_image='static/Images/SkibBot.png'))
        response.set_cookie('session_id', session_id)
        return response
    return render_template('chat.html', past_messages=past_messages, bot_name='SkibBot', bot_image='static/Images/SkibBot.png')

@socketio.on('message')
def handle_message(data):
    username = sanitize_input(data.get('username', ''))
    message = sanitize_input(data.get('text', ''))
    message = censor_message(message)
    ip_id = request.environ.get('REMOTE_ADDR')+":"+str(request.environ.get('REMOTE_PORT'))
    session_id = request.cookies.get('session_id')
    profile_pic = profile_pictures.get(session_id, get_random_profile_image())

    if validate_username(username) and validate_message(message):
        current_time = time.time()
        formatted_datetime = format_datetime(current_time)

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
            emit('message', {'username': 'SkibBot', 'text': f'{username} has been banned for {HACK_BAN_PERIOD // 60} minutes for hacking.', 'color': '#d16262', 'profile_pic': 'static/Images/SkibBot.png'}, broadcast=True)
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
            emit('message', {'username': 'SkibBot', 'text': f'{username} has been banned for {SPAM_BAN_PERIOD} seconds for spamming.', 'color': '#d16262', 'profile_pic': 'static/Images/SkibBot.png'}, broadcast=True)
        else:
            global last_message
            grouped = should_group_message(last_message, session_id, current_time)
            past_messages.append({'type': 'message', 'username': username, 'text': message, 'timestamp': current_time, 'formatted_datetime': formatted_datetime, 'profile_pic': profile_pic, 'grouped': grouped, 'session_id': session_id})
            if len(past_messages) > 30:
                past_messages.pop(0)
            emit('message', {'type': 'message', 'username': username, 'text': message, 'formatted_datetime': formatted_datetime, 'profile_pic': profile_pic, 'grouped': grouped, 'session_id': session_id}, broadcast=True)
            # Update last message tracking
            last_message = {'session_id': session_id, 'timestamp': current_time}
    else:
        emit('error', {'message': 'Please stay below 400 characters.'}, broadcast=False)

@socketio.on('join')
def handle_join(data):
    username = sanitize_input(data.get('username', ''))
    ip_id = request.environ.get('REMOTE_ADDR')+":"+str(request.environ.get('REMOTE_PORT'))
    username_lower = username.lower()
    current_time = time.time()
    session_id = request.cookies.get('session_id')
    profile_pic = profile_pictures.get(session_id, get_random_profile_image())

    if validate_username(username):
        if ip_id not in connected_users:
            connected_users[ip_id] = username
            active_usernames.add(username_lower)
            active_tabs[ip_id] = 1

            profile_pictures[session_id] = profile_pic

            # Check if user is new or returning
            if data.get('is_new_user', True):
                join_message = f'{username} has joined the chat'
                # send_skibbot_message(join_message)

        emit('update user count', {'count': len(active_usernames)}, broadcast=True)
        emit('update online users', {'users': list(active_usernames)}, broadcast=True)
        emit('profile_image_updated', {'image': profile_pic, 'session_id': session_id}, room=request.sid)
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
    old_username = sanitize_input(data.get('old_username', ''))
    new_username = sanitize_input(data.get('new_username', ''))
    ip_id = request.environ.get('REMOTE_ADDR')+":"+str(request.environ.get('REMOTE_PORT'))
    new_username_lower = new_username.lower()
    current_time = time.time()
    session_id = request.cookies.get('session_id')

    last_username_change_time = request.cookies.get('last_username_change_time')
    last_username_change_time = float(last_username_change_time) if last_username_change_time else 0

    if validate_username(new_username):
        if current_time - last_username_change_time < USERNAME_CHANGE_PERIOD:
            remaining_time = int(USERNAME_CHANGE_PERIOD - (current_time - last_username_change_time))
            emit('error', {'message': f"Please wait {remaining_time} seconds before changing your username again."}, broadcast=False)
        else:
            if new_username_lower in active_usernames:
                emit('error', {'message': 'Username already taken'}, broadcast=False)
            else:
                active_usernames.discard(old_username.lower())
                active_usernames.add(new_username_lower)
                connected_users[ip_id] = new_username

                # Update past messages with the new username
                for message in past_messages:
                    if message['username'] == old_username:
                        message['username'] = new_username

                response = make_response(emit('username_changed', {'old_username': old_username, 'new_username': new_username, 'session_id': session_id}, broadcast=True))
                response.set_cookie('last_username_change_time', str(current_time), max_age=7*24*60*60)  # 7 days
                emit('update user count', {'count': len(active_usernames)}, broadcast=True)
                emit('update online users', {'users': list(active_usernames)}, broadcast=True)
                # send_skibbot_message(f"{old_username} changed their username to {new_username}")
                return response
    else:
        emit('error', {'message': 'Invalid username'}, broadcast=False)

@socketio.on('disconnect')
def handle_disconnect():
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
    session_id = request.cookies.get('session_id')
    current_time = time.time()
    profile_pic = profile_pictures.get(session_id, get_random_profile_image())
    formatted_datetime = format_datetime(current_time)

    if validate_username(username) and image_data:
        # Check if the user has uploaded an image within the last 5 minutes
        if session_id in last_image_upload and (current_time - last_image_upload[session_id] < IMAGE_UPLOAD_COOLDOWN):
            remaining_time = int(IMAGE_UPLOAD_COOLDOWN - (current_time - last_image_upload[session_id]))
            minutes, seconds = divmod(remaining_time, 60)
            emit('error', {'message': f"Please wait {minutes}:{seconds:02d} before uploading another image."}, broadcast=False)
        else:
            last_image_upload[session_id] = current_time
            resized_image_data = resize_image(image_data)

            global last_message
            grouped = should_group_message(last_message, session_id, current_time)
            past_messages.append({'type': 'image', 'username': username, 'image': resized_image_data, 'timestamp': current_time, 'formatted_datetime': formatted_datetime, 'profile_pic': profile_pic, 'grouped': grouped, 'session_id': session_id})
            if len(past_messages) > 30:
                past_messages.pop(0)
            emit('image', {'type': 'image', 'username': username, 'image': resized_image_data, 'formatted_datetime': formatted_datetime, 'profile_pic': profile_pic, 'grouped': grouped, 'session_id': session_id}, broadcast=True)
            # Update last message tracking
            last_message = {'session_id': session_id, 'timestamp': current_time}
    else:
        emit('error', {'message': 'Invalid input or missing image data'}, broadcast=False)

@socketio.on('profile_image')
def handle_profile_image(data):
    image_data = data.get('image')
    session_id = request.cookies.get('session_id')
    current_time = time.time()
    last_profile_image_change_time = request.cookies.get('last_profile_image_change_time')
    last_profile_image_change_time = float(last_profile_image_change_time) if last_profile_image_change_time else 0

    if current_time - last_profile_image_change_time < IMAGE_UPLOAD_COOLDOWN:
        remaining_time = int(IMAGE_UPLOAD_COOLDOWN - (current_time - last_profile_image_change_time))
        minutes, seconds = divmod(remaining_time, 60)
        emit('error', {'message': f"Please wait {minutes}:{seconds:02d} before changing your profile image again."}, broadcast=False)
    else:
        if image_data:
            resized_image_data = resize_image(image_data)
            profile_pictures[session_id] = resized_image_data

            response = make_response(emit('profile_image_updated', {'image': resized_image_data, 'session_id': session_id}, broadcast=False))
            response.set_cookie('last_profile_image_change_time', str(current_time), max_age=7*24*60*60)  # 7 days

            # Update all past messages with the new profile image
            for message in past_messages:
                if message['session_id'] == session_id:
                    message['profile_pic'] = resized_image_data
            # Emit an event to update all instances of the profile image for the session
            emit('update_profile_image', {'session_id': session_id, 'profile_pic': resized_image_data}, broadcast=True)
            return response

@socketio.on('clean')
def handle_clean(data):
    for msg in past_messages:
        if msg['type'] == 'message':
            emit('message', {'type': 'message', 'username': msg['username'], 'text': msg['text'], 'formatted_datetime': msg['formatted_datetime'], 'profile_pic': msg['profile_pic'], 'grouped': msg['grouped'], 'session_id': msg['session_id']}, broadcast=False)
        elif msg['type'] == 'image':
            emit('image', {'type': 'image', 'username': msg['username'], 'image': msg['image'], 'formatted_datetime': msg['formatted_datetime'], 'profile_pic': msg['profile_pic'], 'grouped': msg['grouped'], 'session_id': msg['session_id']}, broadcast=False)

if __name__ == '__main__':
    socketio.run(app, debug=True)
