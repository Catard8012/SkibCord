# SkibCord

SkibCord is a real-time web chat built with Flask, designed to mimic Discord while offering a lightweight, customizable alternative. It features instant messaging, custom usernames, mentions, and dynamic notifications to enhance the chat experience.

## Project Structure

- `static/` - Contains CSS, JavaScript, and images for styling and interactive elements.
- `templates/` - Stores `chat.html`, which defines the chat interface.
- `.gitignore` - Specifies ignored files for Git.
- `README.md` - This file, documenting the project.
- `app.py` - The Flask backend for handling chat logic, user interactions, and real-time updates.
- `requirements.txt` - Dependencies needed to run SkibCord.

## Features

- Real-Time Messaging – Messages update instantly without refreshing.
- Custom Usernames – Users can choose and change their names dynamically.
- Mentions & Notifications – Messages highlight when a user is mentioned.
- Dynamic Favicon Badges – Uses `badger.js` to show unread messages in the tab icon.
- Custom Profile Images – Users can upload and change avatars.
- Spam Detection & Bans – Prevents spamming and enforces bans persistently.
- User Status Tracking – Differentiates between "Active Users" and "Online Users."
- Reply & Quoting System – Users can reply to messages with inline quotes.
- Tickle Feature – Double-tap another user’s profile to send a playful tickle.

## Getting Started

### Clone the repository
```sh
git clone https://github.com/Catard8012/SkibCord.git
cd SkibCord
```

### Install dependencies
```sh
pip install -r requirements.txt
```

### Run the Flask server
```sh
python app.py
```

### Open in browser
```
http://127.0.0.1:5000/freak
```

## Customization

- Modify Styles - Edit `static/style.css` for UI adjustments.
- Update Chat Features - Customize `app.py` for new features or bot interactions.
- Enhance Notifications - Adjust `badger.js` to modify favicon alerts.

## Future Enhancements

- Voice & Video Calls – Integrate WebRTC for real-time calls.
- Private Channels & DMs – Implement separate user groups and private chats.
- Pinned Messages – Allow users to save important messages.
- Better Mobile Support – Optimize for mobile usability.

## License

This project is open-source—feel free to modify and expand upon it!

