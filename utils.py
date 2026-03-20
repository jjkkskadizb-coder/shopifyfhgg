# utils.py
import re
import random
import json
import aiohttp
import asyncio
from urllib.parse import quote
from typing import Optional, Dict, Any, Tuple, List

# Import database functions
from database import (
    ensure_user, is_premium_user, is_banned_user,
    get_user_sites, get_random_proxy, remove_proxy_by_url,
    save_card_to_db, add_site_db, remove_site_db
)

# ==================== Card Processing Functions ====================

async def get_bin_info(card_number: str) -> Tuple[str, str, str, str, str, str]:
    """Get BIN information for a card"""
    try:
        bin_number = card_number[:6]
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"https://bins.antipublic.cc/bins/{bin_number}") as res:
                if res.status != 200:
                    return "-", "-", "-", "-", "-", "🏳️"
                response_text = await res.text()
                try:
                    data = json.loads(response_text)
                    brand = data.get('brand', '-')
                    bin_type = data.get('type', '-')
                    level = data.get('level', '-')
                    bank = data.get('bank', '-')
                    country = data.get('country_name', '-')
                    flag = data.get('country_flag', '🏳️')
                    return brand, bin_type, level, bank, country, flag
                except json.JSONDecodeError:
                    return "-", "-", "-", "-", "-", "🏳️"
    except Exception:
        return "-", "-", "-", "-", "-", "🏳️"

def normalize_card(text: str) -> Optional[str]:
    """Normalize card format"""
    if not text:
        return None
    text = text.replace('\n', ' ').replace('/', ' ')
    numbers = re.findall(r'\d+', text)
    cc = mm = yy = cvv = ''
    for part in numbers:
        if len(part) == 16:
            cc = part
        elif len(part) == 4 and part.startswith('20'):
            yy = part[2:]
        elif len(part) == 2 and int(part) <= 12 and mm == '':
            mm = part
        elif len(part) == 2 and not part.startswith('20') and yy == '':
            yy = part
        elif len(part) in [3, 4] and cvv == '':
            cvv = part
    if cc and mm and yy and cvv:
        return f"{cc}|{mm}|{yy}|{cvv}"
    return None

def extract_card(text: str) -> Optional[str]:
    """Extract card from text"""
    match = re.search(r'(\d{12,16})[|\s/]*(\d{1,2})[|\s/]*(\d{2,4})[|\s/]*(\d{3,4})', text)
    if match:
        cc, mm, yy, cvv = match.groups()
        if len(yy) == 4:
            yy = yy[2:]
        return f"{cc}|{mm}|{yy}|{cvv}"
    return normalize_card(text)

def extract_all_cards(text: str) -> List[str]:
    """Extract all cards from text"""
    cards = set()
    for line in text.splitlines():
        card = extract_card(line)
        if card:
            cards.add(card)
    return list(cards)

# ==================== Site Error Keywords ====================

SITE_ERROR_KEYWORDS = [
    'r4 token empty', 'payment method is not shopify', 'r2 id empty',
    'product not found', 'hcaptcha detected', 'hcaptcha_detected',
    'tax ammount empty', 'tax amount empty', 'del ammount empty',
    'product id is empty', 'py id empty', 'clinte token',
    'receipt_empty', 'receipt id is empty', 'receipt empty',
    'na', 'site error! status: 429', 'site error! status: 404',
    'site error! status: 401', 'site error! status: 402',
    'site requires login', 'failed to get token', 'no valid products',
    'not shopify', 'failed to get checkout', 'captcha at checkout',
    'site not supported for now', 'site not supported',
    'connection error', 'error processing card', '504',
    'server error', 'client error', 'amount_too_small',
    'amount too small', 'payments_positive_amount_expected',
    'change proxy or site', 'token not found', 'invalid_response',
    'resolve', 'curl error', 'could not resolve host',
    'connect tunnel failed', 'failed to tokenize card',
    'site error', 'site dead', 'proxy dead',
    'failed to get session token', 'handle is empty',
    'payment method identifier is empty', 'invalid url',
    'error in 1st req', 'error in 1 req', 'cloudflare',
    'connection failed', 'timed out', 'access denied',
    'tlsv1 alert', 'ssl routines', 'could not resolve',
    'domain name not found', 'name or service not known',
    'openssl ssl_connect', 'empty reply from server',
    'httperror504', 'http error', 'timeout', 'unreachable',
    'ssl error', '502', '503', 'bad gateway', 'service unavailable',
    'gateway timeout', 'network error', 'connection reset',
    'failed to detect product', 'failed to create checkout',
    'failed to get proposal data', 'submit rejected',
    'handle error', 'http 404', 'delivery_delivery_line_detail_changed',
    'delivery_address2_required', 'url rejected', 'malformed input',
    'captcha_required', 'captcha required', 'site errors',
    'failed', 'merchandise', 'merchandise_not_enough_stock_on_variant',
    'item',
]

def is_site_error(response_text: str) -> bool:
    """Check if response indicates site error"""
    if not response_text:
        return True
    response_lower = response_text.lower().strip()
    if response_lower == 'na':
        return True
    for keyword in SITE_ERROR_KEYWORDS:
        if keyword in response_lower:
            return True
    return False

def classify_api_response(response_json: dict) -> dict:
    """Classify API response"""
    api_response = str(response_json.get('Response', ''))
    api_status = response_json.get('Status', False)
    price = response_json.get('Price', '-')
    gateway = response_json.get('Gateway', 'Shopify')

    if price is not None and price != '-':
        price = f"${price}"

    response_lower = api_response.lower()

    if is_site_error(api_response):
        return {
            "Response": api_response,
            "Price": price,
            "Gateway": gateway,
            "Status": "SiteError"
        }

    charged_keywords = [
        "order_paid", "order_placed", "order confirmed",
        "thank you", "payment successful", "order completed",
        "charged", "order_created"
    ]

    approved_keywords = [
        "otp_required", "otp required",
        "3d_authentication", "3ds_required", "3d required", "3d_redirect",
        "authentication_required", "insufficient_funds", "insufficient funds",
        "invalid_cvc", "invalid_cvv", "ccn live cvv",
    ]

    declined_keywords = [
        "generic_decline", "generic decline", "do_not_honor", "do not honor",
        "stolen_card", "lost_card", "pickup_card", "pick_up_card",
        "restricted_card", "restricted card", "fraudulent", "fraud suspected",
        "fraud_suspected", "expired_card", "expired card",
        "transaction_not_allowed", "transaction not allowed",
        "card_declined", "card declined", "processor_declined", "processor declined",
        "card_not_supported", "card not supported", "currency_not_supported",
        "duplicate_transaction", "revocation_of_authorization",
        "no_action_taken", "try_again_later", "not_permitted",
        "decline", "your card was declined", "payment_intent_authentication_failure",
        "avs_check_failed", "incorrect number", "incorrect_number",
    ]

    if any(kw in response_lower for kw in charged_keywords):
        return {"Response": api_response, "Price": price, "Gateway": gateway, "Status": "Charged"}

    if any(kw in response_lower for kw in declined_keywords):
        return {"Response": api_response, "Price": price, "Gateway": gateway, "Status": "Declined"}

    if any(kw in response_lower for kw in approved_keywords):
        return {"Response": api_response, "Price": price, "Gateway": gateway, "Status": "Approved"}

    if api_status is True:
        if not any(word in response_lower for word in ["decline", "denied", "failed", "error", "rejected", "refused", "fraud"]):
            return {"Response": api_response, "Price": price, "Gateway": gateway, "Status": "Approved"}

    return {"Response": api_response, "Price": price, "Gateway": gateway, "Status": "Declined"}

def get_status_header(status: str) -> str:
    """Get status header for display"""
    if status == "Charged":
        return "CHARGED 💎"
    elif status == "Approved":
        return "APPROVED ✅"
    elif status == "Proxy Dead":
        return "PROXY DEAD ⚠️"
    elif status == "Error" or status == "SiteError":
        return "~~ ERROR ~~ ⚠️"
    else:
        return "~~ DECLINED ~~ ❌"

# ==================== API Request Functions ====================

async def check_card_specific_site(card: str, site: str, user_id: int = None) -> dict:
    """Check card on specific site"""
    proxy_data = await get_random_proxy(user_id) if user_id else None

    try:
        if not site.startswith('http'):
            site = f'https://{site}'

        proxy_str = None
        if proxy_data:
            ip = proxy_data.get('ip')
            port = proxy_data.get('port')
            username = proxy_data.get('username')
            password = proxy_data.get('password')
            if username and password:
                proxy_str = f"{ip}:{port}:{username}:{password}"
            else:
                proxy_str = f"{ip}:{port}"

        encoded_cc = quote(card, safe='')
        encoded_site = quote(site, safe='')
        url = f'?site={encoded_site}&cc={encoded_cc}'
        if proxy_str:
            encoded_proxy = quote(proxy_str, safe='')
            url += f'&proxy={encoded_proxy}'

        timeout = aiohttp.ClientTimeout(total=100)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as res:
                if res.status != 200:
                    return {"Response": f"HTTP_ERROR_{res.status}", "Price": "-", "Gateway": "-", "Status": "SiteError"}

                try:
                    response_json = await res.json()
                except Exception:
                    response_text = await res.text()
                    return {"Response": f"Invalid JSON: {response_text[:100]}", "Price": "-", "Gateway": "-", "Status": "SiteError"}

                if proxy_data and user_id:
                    resp_lower = str(response_json.get('Response', '')).lower()
                    if 'proxy' in resp_lower and ('dead' in resp_lower or 'error' in resp_lower or 'timeout' in resp_lower):
                        await remove_proxy_by_url(user_id, proxy_data.get('proxy_url'))
                        return {
                            "Response": "Proxy is dead and has been removed! Please add a new proxy using /addpxy",
                            "Price": "-", "Gateway": "-", "Status": "Proxy Dead"
                        }

                result = classify_api_response(response_json)
                return result

    except Exception as e:
        return {"Response": str(e), "Price": "-", "Gateway": "-", "Status": "SiteError"}

async def check_card_random_site(card: str, sites: list, user_id: int = None) -> tuple:
    """Check card on random site"""
    if not sites:
        return {"Response": "ERROR", "Price": "-", "Gateway": "-", "Status": "Error"}, -1
    selected_site = random.choice(sites)
    site_index = sites.index(selected_site) + 1
    result = await check_card_specific_site(card, selected_site, user_id)
    return result, site_index

async def check_card_with_retry(card: str, sites: list, user_id: int = None, max_retries: int = 3) -> tuple:
    """Check card with retry on error"""
    for attempt in range(max_retries):
        if not sites:
            return {"Response": "No sites available", "Price": "-", "Gateway": "-", "Status": "Error"}, -1

        selected_site = random.choice(sites)
        site_index = sites.index(selected_site) + 1

        result = await check_card_specific_site(card, selected_site, user_id)

        if result.get("Status") == "SiteError":
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                continue
            else:
                result["Status"] = "Error"
                return result, site_index

        return result, site_index

    return {"Response": "Max retries exceeded", "Price": "-", "Gateway": "-", "Status": "Error"}, -1

async def test_single_site(site: str, test_card: str = "4031630422575208|01|2030|280", user_id: int = None) -> dict:
    """Test if a site is working"""
    try:
        if not site.startswith('http'):
            site = f'https://{site}'

        proxy_data = await get_random_proxy(user_id) if user_id else None

        proxy_str = None
        if proxy_data:
            ip = proxy_data.get('ip')
            port = proxy_data.get('port')
            username = proxy_data.get('username')
            password = proxy_data.get('password')
            if username and password:
                proxy_str = f"{ip}:{port}:{username}:{password}"
            else:
                proxy_str = f"{ip}:{port}"

        encoded_cc = quote(test_card, safe='')
        encoded_site = quote(site, safe='')
        url = f'?site={encoded_site}&cc={encoded_cc}'
        if proxy_str:
            encoded_proxy = quote(proxy_str, safe='')
            url += f'&proxy={encoded_proxy}'

        timeout = aiohttp.ClientTimeout(total=90)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as res:
                if res.status != 200:
                    return {"status": "dead", "response": f"HTTP {res.status}", "site": site, "price": "-"}

                try:
                    response_json = await res.json()
                except Exception:
                    response_text = await res.text()
                    return {"status": "dead", "response": f"Invalid JSON: {response_text[:100]}", "site": site, "price": "-"}

                response_msg = response_json.get("Response", "")
                price = response_json.get("Price", "-")
                if price is not None and price != '-':
                    price = f"${price}"

                if proxy_data and user_id:
                    resp_lower = str(response_msg).lower()
                    if 'proxy' in resp_lower and ('dead' in resp_lower or 'error' in resp_lower or 'timeout' in resp_lower):
                        await remove_proxy_by_url(user_id, proxy_data.get('proxy_url'))
                        return {"status": "proxy_dead", "response": "Proxy is dead and has been removed!", "site": site, "price": "-"}

                if is_site_error(response_msg):
                    return {"status": "dead", "response": response_msg, "site": site, "price": price}
                else:
                    return {"status": "working", "response": response_msg, "site": site, "price": price}
    except Exception as e:
        return {"status": "dead", "response": str(e), "site": site, "price": "-"}

def get_cc_limit(access_type: str, user_id: int = None) -> int:
    """Get CC limit based on access type"""
    from config import ADMIN_ID
    if user_id and user_id in ADMIN_ID:
        return 2000
    if access_type in ["premium_private", "premium_group"]:
        return 500
    elif access_type == "group_free":
        return 50
    return 0
