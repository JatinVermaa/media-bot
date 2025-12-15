import asyncio
from telethon import TelegramClient, events, Button
import os
import re
import io

# === CONFIGURATION ===
API_ID = 22431572
API_HASH = "10c56acead2d26889681bbf683963e7b"
BOT_TOKEN = "8509538843:AAHgaPqFC4GJcrpS7ixvn-psAHuFxnxsHJo"

# === CLEAN OLD SESSIONS (optional, for testing) ===
for file in ["bot_session.session", "user_session.session"]:
    if os.path.exists(file):
        os.remove(file)

# === INITIALIZE TELETHON CLIENTS ===
bot = TelegramClient("bot_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)
user_client = TelegramClient("user_session", API_ID, API_HASH)

# Store per-user context
user_data = {}

# === BOT COMMAND HANDLERS ===
@bot.on(events.NewMessage(pattern="/start"))
async def start(event):
    await event.respond(
        "👋 Welcome!\n\nSend me the **link of your private/public channel or group** (you must be admin).",
        buttons=[Button.text("Cancel", resize=True)]
    )

@bot.on(events.NewMessage)
async def main_handler(event):
    text = event.raw_text.strip()

    # Step 1: Detect source link
    if re.match(r"(https?://t\.me/[\w_]+|https?://t\.me/\+[\w_-]+)", text):
        user_data[event.sender_id] = {"source": text}
        await event.respond("✅ Got the source link!\nNow send the **destination channel username** (e.g. @MyChannel).")
        return

    # Step 2: Detect destination channel username
    if text.startswith("@"):
        if event.sender_id not in user_data or "source" not in user_data[event.sender_id]:
            await event.respond("❌ Please send the source link first.")
            return

        source = user_data[event.sender_id]["source"]
        dest = text
        await event.respond(f"📥 Starting media transfer...\nFrom: {source}\nTo: {dest}")

        # Run the transfer
        await transfer_media(event, source, dest)

async def transfer_media(event, source, dest):
    """Main logic: forward if possible, else download+upload."""
    async with user_client:
        total = 0
        forwarded = 0
        reuploaded = 0
        failed = 0
        tasks = []

        async for msg in user_client.iter_messages(source, limit=None):
            if not msg.media:
                continue
            total += 1

            try:
                # Try to forward first
                await user_client.forward_messages(dest, msg)
                forwarded += 1
            except Exception:
                # If forwarding fails (forward restricted), use reupload
                tasks.append(asyncio.create_task(upload_message(user_client, msg, dest)))
                reuploaded += 1

            # Upload in batches of 10 concurrently
            if len(tasks) >= 10:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                failed += sum(1 for r in results if isinstance(r, Exception))
                tasks.clear()

        # Process remaining uploads
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            failed += sum(1 for r in results if isinstance(r, Exception))

        await event.respond(
            f"✅ Transfer complete!\n\n"
            f"Total media checked: {total}\n"
            f"Forwarded directly: {forwarded}\n"
            f"Reuploaded manually: {reuploaded}\n"
            f"Failed uploads: {failed}"
        )

async def upload_message(client, msg, dest):
    """Download media in-memory and upload to destination."""
    try:
        data = await msg.download_media(file=bytes)
        if not data:
            return
        buffer = io.BytesIO(data)
        buffer.name = "media"
        await client.send_file(dest, buffer, caption=msg.text or "")
    except Exception as e:
        print(f"[UPLOAD ERROR] {e}")
        raise

print("🤖 Bot is running... (Press Ctrl+C to stop)")
bot.run_until_disconnected()
