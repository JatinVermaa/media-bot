import json
import os
import uuid
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- Credentials ---
api_id = 22431572
api_hash = "10c56acead2d26889681bbf683963e7b"
bot_token = "8078540294:AAGt1ptw5aZ5fRHNmSxmqD_1tq-rOdw0ryQ"
channel_id = 8275146193

# Allowed users list
allowed_users = [8275146193, 7291132221, 8333162009, 7984344345]

# --- JSON Safe Loader ---
def load_json(filename):
    """Load JSON file safely and auto-reset if corrupted."""
    if not os.path.exists(filename):
        return {}
    try:
        with open(filename, "r", encoding="utf-8") as f:  # <-- UTF-8 added
            return json.load(f)
    except json.JSONDecodeError:
        print(f"⚠️ JSON error in {filename}, resetting file.")
        with open(filename, "w", encoding="utf-8") as f:  # <-- UTF-8 added
            f.write("{}")
        return {}

def save_json(filename, data):
    """Save JSON data safely."""
    with open(filename, "w", encoding="utf-8") as f:  # <-- UTF-8 added
        json.dump(data, f, ensure_ascii=False, indent=4)  # <-- keep emojis

# Initialize the bot
app = Client("media_getter", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

# Load or initialize the databases
links_db = load_json("links.json")
users_db = load_json("users.json")

# Temporary dictionary to track user states
user_states = {}

# --- Save users automatically ---
def save_user_info(user):
    users = load_json("users.json")
    user_id = str(user.id)
    users[user_id] = {
        "name": user.first_name,
        "username": user.username or "N/A"
    }
    save_json("users.json", users)

# --- /start handler with deep link support ---
@app.on_message(filters.command("start"))
def start(client, message):
    user_id = message.from_user.id
    save_user_info(message.from_user)

    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        # Deep link mode: /start <link_id>
        link_id = args[1].strip()
        if link_id in links_db:
            info = links_db[link_id]
            message.reply("Fetching your media...")
            for msg_id in info["media"]:
                client.copy_message(chat_id=message.chat.id, from_chat_id=channel_id, message_id=msg_id)
            label = info.get("label", "No Label")
            message.reply(f"Label: {label}")
            return
        else:
            message.reply("Invalid link.")
            return

    # Normal start buttons
    if user_id in allowed_users:
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("Save Your Media 📁", callback_data="save_media")],
            [InlineKeyboardButton("All Codes 📋", callback_data="all_codes")],
            [InlineKeyboardButton("Delete Link ❌", callback_data="delete_link")],
            [InlineKeyboardButton("All Users 👥", callback_data="all_users")]
        ])
    else:
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("Get Media By Link 🔗", callback_data="get_media")]
        ])
    message.reply("Welcome! Choose an option:", reply_markup=buttons)

# --- Handle button presses ---
@app.on_callback_query()
def handle_buttons(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data

    if data == "save_media":
        if user_id not in allowed_users:
            callback_query.answer("YOU ARE NOT PERMITTED TO USE THIS BOT", show_alert=True)
            return
        callback_query.message.reply("Send me the media files you want to save. When done, type /done.")
        user_states[user_id] = {"mode": "saving", "media": []}
        callback_query.answer()

    elif data == "all_codes":
        if user_id not in allowed_users:
            callback_query.answer("YOU ARE NOT PERMITTED TO USE THIS BOT", show_alert=True)
            return
        text = "All stored links:\n"
        bot_username = client.get_me().username
        for link_id, info in links_db.items():
            label = info.get("label", "No Label")
            deep_link = f"https://t.me/{bot_username}?start={link_id}"
            text += f"Label: {label} ➝ {deep_link}\n"
        callback_query.message.reply(text or "No links available.")
        callback_query.answer()

    elif data == "delete_link":
        if user_id not in allowed_users:
            callback_query.answer("YOU ARE NOT PERMITTED TO USE THIS BOT", show_alert=True)
            return
        callback_query.message.reply("Please send the link ID you want to delete.")
        user_states[user_id] = {"mode": "deleting"}
        callback_query.answer()

    elif data == "all_users":
        if user_id not in allowed_users:
            callback_query.answer("YOU ARE NOT PERMITTED TO USE THIS BOT", show_alert=True)
            return

        users = load_json("users.json")
        if not users:
            callback_query.message.reply("No users found yet.")
            return

        text = "👥 All Users:\n"
        for i, (uid, info) in enumerate(users.items(), start=1):
            text += f"{i}. {info['name']} (@{info['username']}) ➝ ID: {uid}\n"
        text += "\nSend a name or user ID to select a user."

        user_states[user_id] = {"mode": "select_user"}
        callback_query.message.reply(text)
        callback_query.answer()

# --- Handle media messages ---
@app.on_message(filters.media)
def media_handler(client, message):
    user_id = message.from_user.id
    if user_id in user_states and user_states[user_id].get("mode") == "saving":
        user_states[user_id]["media"].append(message.id)

# --- Handle /done command ---
@app.on_message(filters.command("done"))
def done_handler(client, message):
    user_id = message.from_user.id
    state = user_states.get(user_id)
    if not state or state.get("mode") != "saving":
        message.reply("You are not currently saving media.")
        return
    if not state.get("media"):
        message.reply("No media has been added.")
        return
    user_states[user_id]["mode"] = "await_label"
    message.reply("All media received. Please send the label you want to assign to this media batch.")

# --- Handle text input ---
@app.on_message(filters.text & ~filters.command(["start", "done"]))
def text_handler(client, message):
    user_id = message.from_user.id
    state = user_states.get(user_id)

    # Handle label after /done
    if state and state.get("mode") == "await_label":
        label = message.text.strip()
        media_list = state.get("media")
        link_id = uuid.uuid4().hex[:8]
        forwarded_ids = []
        for msg_id in media_list:
            forwarded = client.forward_messages(
                chat_id=channel_id,
                from_chat_id=message.chat.id,
                message_ids=msg_id
            )
            forwarded_ids.append(forwarded.id)
        links_db[link_id] = {"media": forwarded_ids, "label": label}
        save_json("links.json", links_db)

        bot_username = client.get_me().username
        deep_link = f"https://t.me/{bot_username}?start={link_id}"
        message.reply(f"Media saved with label '{label}'.\nHere is your link:\n{deep_link}")
        del user_states[user_id]
        return

    # Handle delete_link
    if state and state.get("mode") == "deleting":
        link_id = message.text.strip()
        if link_id not in links_db:
            message.reply("Invalid link ID.")
            return
        del links_db[link_id]
        save_json("links.json", links_db)
        message.reply(f"Link {link_id} deleted successfully.")
        del user_states[user_id]
        return

    # Handle user selection (search)
    if state and state.get("mode") == "select_user":
        search_term = message.text.strip().lower()
        users = load_json("users.json")

        found_user = None
        for uid, info in users.items():
            if search_term in info["name"].lower() or search_term == uid:
                found_user = {"id": int(uid), "name": info["name"]}
                break

        if not found_user:
            message.reply("No matching user found. Try again.")
            return

        user_states[user_id] = {"mode": "send_label", "target_user": found_user}
        message.reply(f"User found: {found_user['name']}.\nNow send me the label to forward media from.")
        return

    # Handle sending labeled media to selected user
    if state and state.get("mode") == "send_label":
        label = message.text.strip()
        found_user = state["target_user"]
        target_user_id = found_user["id"]

        found_label = None
        for link_id, info in links_db.items():
            if info.get("label", "").lower() == label.lower():
                found_label = info
                break

        if not found_label:
            message.reply("Label not found.")
            return

        message.reply(f"Sending media with label '{label}' to {found_user['name']}...")
        for msg_id in found_label["media"]:
            try:
                client.copy_message(chat_id=target_user_id, from_chat_id=channel_id, message_id=msg_id)
            except Exception as e:
                print(e)
                continue

        message.reply("✅ Media sent successfully.")
        del user_states[user_id]
        return

# --- Run the bot ---
if __name__ == "__main__":
    print("Bot is running...")
    app.run()
