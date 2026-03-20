# bot_core.py
from telethon import TelegramClient, events, Button
from telethon.tl.types import KeyboardButtonCallback
import requests, random, datetime, json, os, re, asyncio, time
import string
import hashlib
import aiohttp
import aiofiles
from urllib.parse import urlparse, quote

# Import database
from database import (
    init_db, db,
    ensure_user, get_user, is_premium_user, add_premium_user, remove_premium,
    is_banned_user, ban_user, unban_user,
    create_key, get_key_data, use_key, get_all_keys,
    add_proxy_db, get_all_user_proxies, get_proxy_count, get_random_proxy,
    remove_proxy_by_index, remove_proxy_by_url, clear_all_proxies,
    add_site_db, get_user_sites, remove_site_db, clear_user_sites, set_user_sites,
    save_card_to_db, get_total_cards_count, get_charged_count, get_approved_count,
    get_all_premium_users, get_total_users, get_premium_count,
    get_total_sites_count, get_users_with_sites, get_sites_per_user, get_all_sites_detail
)

# Import utility functions
from utils import (
    get_bin_info, normalize_card, extract_card, extract_all_cards,
    is_site_error, classify_api_response, get_status_header,
    check_card_specific_site, check_card_random_site, check_card_with_retry,
    test_single_site, get_cc_limit, parse_proxy_format, test_proxy,
    is_valid_url_or_domain, extract_urls_from_text
)

# Import config
from config import API_ID, API_HASH, BOT_TOKEN, ADMIN_ID, GROUP_ID

# Global variables
ACTIVE_MTXT_PROCESSES = {}
TEMP_WORKING_SITES = {}
USER_APPROVED_PREF = {}

client = TelegramClient('cc_bot', API_ID, API_HASH)

# ==================== Utility Functions ====================

def generate_key():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))

async def can_use(user_id, chat):
    if await is_banned_user(user_id):
        return False, "banned"
    
    is_prem = await is_premium_user(user_id)
    is_private = chat.id == user_id
    
    if is_private:
        if is_prem:
            return True, "premium_private"
        else:
            return False, "no_access"
    else:
        if is_prem:
            return True, "premium_group"
        else:
            return True, "group_free"

async def save_approved_card(card, status, response, gateway, price):
    try:
        await save_card_to_db(card, status, response or '', gateway or '', price or '')
    except Exception as e:
        print(f"Error saving card to DB: {str(e)}")

async def pin_charged_message(event, message):
    try:
        if event.is_group:
            await message.pin()
    except Exception as e:
        print(f"Failed to pin message: {e}")

async def send_hit_notification(client_instance, card, result, username, user_id):
    try:
        price = result.get('Price', '-')
        response = result.get('Response', '-')
        gateway = result.get('Gateway', 'Shopify')
        status = result.get('Status', 'Charged')
        
        if status == "Charged":
            emoji = "💎"
            status_text = "𝐂𝐇𝐀𝐑𝐆𝐄𝐃"
        else:
            emoji = "✅"
            status_text = "𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃"
        
        hit_msg = f"""{emoji} 𝐇𝐈𝐓 𝐃𝐄𝐓𝐄𝐂𝐓𝐄𝐃 {emoji}

𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 ➔ {response}
𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ➔ {gateway}
𝐏𝐫𝐢𝐜𝐞 ➔ {price}

𝐔𝐬𝐞𝐫 ➔ @{username}"""
        
        try:
            await client_instance.send_message(GROUP_ID, hit_msg)
        except Exception as e:
            print(f"Failed to send hit to group: {e}")
    
    except Exception as e:
        print(f"Error sending hit notification: {e}")

def banned_user_message():
    return "🚫 **You Are Banned!**\n\nYou are not allowed to use this bot.\n\nFor appeal, contact @Mod_By_Kamal"

def access_denied_message_with_button():
    message = "🚫 **Access Denied!** This command requires premium access or group usage."
    buttons = [[Button.url("🚀 Join Group for Free Access", "https://t.me/+pNplrRLrEGY5NTU0")]]
    return message, buttons

# ==================== Bot Command Handlers ====================

@client.on(events.NewMessage(pattern=r'(?i)^[/.](start|cmds?|commands?)$'))
async def start(event):
    await ensure_user(event.sender_id)
    _, access_type = await can_use(event.sender_id, event.chat)
    if access_type == "banned":
        return await event.reply(banned_user_message())
    
    text = """🚀 **Hello and welcome!**

Here are the available command categories.

** Shopify Self **
`/sh` ⇾ Check a single CC.
`/msh` ⇾ Check multiple CCs from text.
`/mtxt` ⇾ Check CCs from a `.txt` file.
`/ran` ⇾ Check CCs from `.txt` using random sites.

** Bot & User Management **
`/add` <site> ⇾ Add site(s) to your DB.
`/rm` <site> ⇾ Remove site(s) from your DB.
`/check` ⇾ Test your saved sites.
`/info` ⇾ Get your user information.
`/redeem` <key> ⇾ Redeem a premium key.

** Proxy Management (Private Only) **
`/addpxy` <proxy> ⇾ Add proxy (max 10, ip:port:user:pass).
`/proxy` ⇾ View all your saved proxies.
`/rmpxy` <index|all> ⇾ Remove proxy by index or all.
"""
    
    if access_type in ["premium_private", "premium_group"]:
        text += f"\n💎 **Status:** Premium Access (`{get_cc_limit(access_type, event.sender_id)}` CCs)"
    else:
        text += f"\n🆓 **Status:** Group User (`{get_cc_limit(access_type, event.sender_id)}` CCs)"
    
    await event.reply(text)

# Add all other bot handlers here (sh, msh, mtxt, etc.)
# ... (copy all other handlers from your bot.py)

async def main():
    await init_db()
    print("BOT RUNNING 💨")
    await client.start(bot_token=BOT_TOKEN)
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
