# api.py
from fastapi import FastAPI, HTTPException, Depends, Header, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import uvicorn
import asyncio
import json
from datetime import datetime
import re

# Import database functions
from database import (
    init_db, ensure_user, get_user, is_premium_user,
    add_premium_user, remove_premium, is_banned_user,
    create_key, get_key_data, use_key, get_all_keys,
    add_proxy_db, get_all_user_proxies, get_proxy_count,
    get_random_proxy, remove_proxy_by_index, remove_proxy_by_url,
    clear_all_proxies, add_site_db, get_user_sites,
    remove_site_db, clear_user_sites, set_user_sites,
    save_card_to_db, get_total_cards_count, get_charged_count,
    get_approved_count, get_all_premium_users, get_total_users,
    get_premium_count, get_total_sites_count, get_users_with_sites,
    get_sites_per_user, get_all_sites_detail
)

# Import utility functions from bot
from bot import (
    check_card_specific_site, check_card_random_site,
    check_card_with_retry, extract_card, extract_all_cards,
    get_bin_info, normalize_card, get_status_header,
    is_site_error, classify_api_response, test_single_site,
    get_cc_limit, can_use
)

# FastAPI app
app = FastAPI(
    title="CC Checker Bot API",
    description="API for credit card checking bot",
    version="1.0.0"
)

# ==================== Request/Response Models ====================

class CardCheckRequest(BaseModel):
    card: str = Field(..., description="Credit card in format: 4111111111111111|12|2025|123")
    user_id: int = Field(..., description="Telegram user ID")
    site: Optional[str] = Field(None, description="Specific site to check (optional)")
    max_retries: int = Field(3, ge=1, le=5, description="Maximum retry attempts")

class BulkCardCheckRequest(BaseModel):
    cards: List[str] = Field(..., description="List of credit cards")
    user_id: int = Field(..., description="Telegram user ID")
    site: Optional[str] = Field(None, description="Specific site to check (optional)")
    max_retries: int = Field(3, ge=1, le=5)

class SiteRequest(BaseModel):
    user_id: int = Field(..., description="Telegram user ID")
    site: str = Field(..., description="Site URL or domain")

class BulkSiteRequest(BaseModel):
    user_id: int = Field(..., description="Telegram user ID")
    sites: List[str] = Field(..., description="List of site URLs or domains")

class ProxyRequest(BaseModel):
    user_id: int = Field(..., description="Telegram user ID")
    proxy: str = Field(..., description="Proxy in format: ip:port:user:pass or ip:port")

class ProxyRemoveRequest(BaseModel):
    user_id: int = Field(..., description="Telegram user ID")
    index: Optional[int] = Field(None, description="Proxy index to remove")
    remove_all: bool = Field(False, description="Remove all proxies")

class KeyRequest(BaseModel):
    key: str = Field(..., description="Premium key")
    user_id: int = Field(..., description="Telegram user ID")

class UserRequest(BaseModel):
    user_id: int = Field(..., description="Telegram user ID")

class AdminAuthRequest(BaseModel):
    user_id: int = Field(..., description="User ID to grant premium")
    days: int = Field(..., description="Number of days")

# ==================== Authentication ====================

async def verify_api_key(api_key: str = Header(..., alias="X-API-Key")):
    """Verify API key (you should implement your own auth system)"""
    # For production, store valid API keys in database
    valid_keys = ["your-api-key-here", "test-key-123"]
    if api_key not in valid_keys:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return api_key

# ==================== Card Checking Endpoints ====================

@app.post("/api/v1/check", response_model=Dict[str, Any])
async def check_card(request: CardCheckRequest, api_key: str = Depends(verify_api_key)):
    """
    Check a single credit card
    """
    try:
        # Ensure user exists
        await ensure_user(request.user_id)
        
        # Check if user is banned
        if await is_banned_user(request.user_id):
            raise HTTPException(status_code=403, detail="User is banned")
        
        # Extract and normalize card
        normalized_card = extract_card(request.card)
        if not normalized_card:
            raise HTTPException(status_code=400, detail="Invalid card format")
        
        # Get user sites
        user_sites = await get_user_sites(request.user_id)
        if not user_sites:
            raise HTTPException(status_code=400, detail="No sites added for user")
        
        # Check card
        if request.site:
            result = await check_card_specific_site(normalized_card, request.site, request.user_id)
            site_index = 1
        else:
            result, site_index = await check_card_with_retry(
                normalized_card, user_sites, request.user_id, request.max_retries
            )
        
        # Get BIN info
        card_number = normalized_card.split("|")[0]
        brand, bin_type, level, bank, country, flag = await get_bin_info(card_number)
        
        # Save result if charged or approved
        status = result.get("Status", "Declined")
        if status in ["Charged", "Approved"]:
            await save_card_to_db(
                normalized_card, 
                status, 
                result.get("Response", ""), 
                result.get("Gateway", ""), 
                result.get("Price", "")
            )
        
        return {
            "success": True,
            "card": normalized_card,
            "status": status,
            "status_display": get_status_header(status),
            "response": result.get("Response", ""),
            "gateway": result.get("Gateway", "Unknown"),
            "price": result.get("Price", "-"),
            "site_index": site_index if not request.site else 1,
            "bin_info": {
                "brand": brand,
                "type": bin_type,
                "level": level,
                "bank": bank,
                "country": country,
                "flag": flag
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/check/bulk", response_model=Dict[str, Any])
async def check_cards_bulk(request: BulkCardCheckRequest, api_key: str = Depends(verify_api_key)):
    """
    Check multiple credit cards
    """
    try:
        await ensure_user(request.user_id)
        
        if await is_banned_user(request.user_id):
            raise HTTPException(status_code=403, detail="User is banned")
        
        # Get user sites
        user_sites = await get_user_sites(request.user_id)
        if not user_sites:
            raise HTTPException(status_code=400, detail="No sites added for user")
        
        results = []
        for card in request.cards[:20]:  # Limit to 20 cards
            normalized_card = extract_card(card)
            if not normalized_card:
                continue
                
            if request.site:
                result = await check_card_specific_site(normalized_card, request.site, request.user_id)
                site_index = 1
            else:
                result, site_index = await check_card_with_retry(
                    normalized_card, user_sites, request.user_id, request.max_retries
                )
            
            # Get BIN info
            card_number = normalized_card.split("|")[0]
            brand, bin_type, level, bank, country, flag = await get_bin_info(card_number)
            
            status = result.get("Status", "Declined")
            if status in ["Charged", "Approved"]:
                await save_card_to_db(
                    normalized_card, 
                    status, 
                    result.get("Response", ""), 
                    result.get("Gateway", ""), 
                    result.get("Price", "")
                )
            
            results.append({
                "card": normalized_card,
                "status": status,
                "status_display": get_status_header(status),
                "response": result.get("Response", ""),
                "gateway": result.get("Gateway", "Unknown"),
                "price": result.get("Price", "-"),
                "site_index": site_index,
                "bin_info": {
                    "brand": brand,
                    "type": bin_type,
                    "level": level,
                    "bank": bank,
                    "country": country,
                    "flag": flag
                }
            })
        
        return {
            "success": True,
            "total": len(results),
            "results": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== Site Management Endpoints ====================

@app.post("/api/v1/sites/add", response_model=Dict[str, Any])
async def add_site(request: SiteRequest, api_key: str = Depends(verify_api_key)):
    """
    Add a site for user
    """
    try:
        await ensure_user(request.user_id)
        
        if await is_banned_user(request.user_id):
            raise HTTPException(status_code=403, detail="User is banned")
        
        success = await add_site_db(request.user_id, request.site)
        
        return {
            "success": success,
            "site": request.site,
            "message": "Site added successfully" if success else "Site already exists"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/sites/add/bulk", response_model=Dict[str, Any])
async def add_sites_bulk(request: BulkSiteRequest, api_key: str = Depends(verify_api_key)):
    """
    Add multiple sites for user
    """
    try:
        await ensure_user(request.user_id)
        
        if await is_banned_user(request.user_id):
            raise HTTPException(status_code=403, detail="User is banned")
        
        added = []
        existing = []
        
        for site in request.sites:
            success = await add_site_db(request.user_id, site)
            if success:
                added.append(site)
            else:
                existing.append(site)
        
        return {
            "success": True,
            "added": added,
            "existing": existing,
            "total_added": len(added),
            "message": f"Added {len(added)} sites, {len(existing)} already existed"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/v1/sites/remove", response_model=Dict[str, Any])
async def remove_site(request: SiteRequest, api_key: str = Depends(verify_api_key)):
    """
    Remove a site for user
    """
    try:
        await ensure_user(request.user_id)
        
        if await is_banned_user(request.user_id):
            raise HTTPException(status_code=403, detail="User is banned")
        
        success = await remove_site_db(request.user_id, request.site)
        
        return {
            "success": success,
            "site": request.site,
            "message": "Site removed successfully" if success else "Site not found"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/sites/{user_id}", response_model=Dict[str, Any])
async def get_user_sites_endpoint(user_id: int, api_key: str = Depends(verify_api_key)):
    """
    Get all sites for a user
    """
    try:
        await ensure_user(user_id)
        
        if await is_banned_user(user_id):
            raise HTTPException(status_code=403, detail="User is banned")
        
        sites = await get_user_sites(user_id)
        
        return {
            "success": True,
            "user_id": user_id,
            "total": len(sites),
            "sites": sites
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/sites/clear/{user_id}", response_model=Dict[str, Any])
async def clear_user_sites_endpoint(user_id: int, api_key: str = Depends(verify_api_key)):
    """
    Clear all sites for a user
    """
    try:
        await ensure_user(user_id)
        
        if await is_banned_user(user_id):
            raise HTTPException(status_code=403, detail="User is banned")
        
        success = await clear_user_sites(user_id)
        
        return {
            "success": success,
            "user_id": user_id,
            "message": "All sites cleared" if success else "Failed to clear sites"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/sites/test", response_model=Dict[str, Any])
async def test_site(request: SiteRequest, api_key: str = Depends(verify_api_key)):
    """
    Test if a site is working
    """
    try:
        await ensure_user(request.user_id)
        
        result = await test_single_site(request.site, user_id=request.user_id)
        
        return {
            "success": True,
            "site": request.site,
            "status": result.get("status"),
            "response": result.get("response"),
            "price": result.get("price")
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== Proxy Management Endpoints ====================

@app.post("/api/v1/proxy/add", response_model=Dict[str, Any])
async def add_proxy(request: ProxyRequest, api_key: str = Depends(verify_api_key)):
    """
    Add a proxy for user
    """
    try:
        await ensure_user(request.user_id)
        
        if await is_banned_user(request.user_id):
            raise HTTPException(status_code=403, detail="User is banned")
        
        # Import parse_proxy_format and test_proxy from bot
        from bot import parse_proxy_format, test_proxy
        
        proxy_data = parse_proxy_format(request.proxy)
        if not proxy_data:
            raise HTTPException(status_code=400, detail="Invalid proxy format")
        
        # Check limit
        current_count = await get_proxy_count(request.user_id)
        if current_count >= 10:
            raise HTTPException(status_code=400, detail="Proxy limit reached (max 10)")
        
        # Test proxy
        is_working, result = await test_proxy(proxy_data['proxy_url'])
        if not is_working:
            raise HTTPException(status_code=400, detail=f"Proxy not working: {result}")
        
        # Add to database
        await add_proxy_db(request.user_id, proxy_data)
        new_count = current_count + 1
        
        return {
            "success": True,
            "proxy": {
                "ip": proxy_data['ip'],
                "port": proxy_data['port'],
                "type": proxy_data.get('type', 'http'),
                "has_auth": bool(proxy_data.get('username'))
            },
            "external_ip": result,
            "total_proxies": new_count,
            "message": "Proxy added successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/proxy/{user_id}", response_model=Dict[str, Any])
async def get_user_proxies(user_id: int, api_key: str = Depends(verify_api_key)):
    """
    Get all proxies for a user
    """
    try:
        await ensure_user(user_id)
        
        if await is_banned_user(user_id):
            raise HTTPException(status_code=403, detail="User is banned")
        
        proxies = await get_all_user_proxies(user_id)
        
        proxy_list = []
        for idx, proxy in enumerate(proxies, 1):
            proxy_list.append({
                "index": idx,
                "ip": proxy.get('ip'),
                "port": proxy.get('port'),
                "type": proxy.get('proxy_type', 'http'),
                "has_auth": bool(proxy.get('username')),
                "username": proxy.get('username'),
                "proxy_url": proxy.get('proxy_url')
            })
        
        return {
            "success": True,
            "user_id": user_id,
            "total": len(proxy_list),
            "proxies": proxy_list
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/v1/proxy/remove", response_model=Dict[str, Any])
async def remove_proxy(request: ProxyRemoveRequest, api_key: str = Depends(verify_api_key)):
    """
    Remove a proxy for user
    """
    try:
        await ensure_user(request.user_id)
        
        if await is_banned_user(request.user_id):
            raise HTTPException(status_code=403, detail="User is banned")
        
        if request.remove_all:
            count = await clear_all_proxies(request.user_id)
            return {
                "success": True,
                "removed": count,
                "message": f"Removed {count} proxies"
            }
        elif request.index is not None:
            removed = await remove_proxy_by_index(request.user_id, request.index - 1)
            if removed:
                return {
                    "success": True,
                    "removed": removed,
                    "message": f"Proxy {request.index} removed successfully"
                }
            else:
                raise HTTPException(status_code=404, detail="Proxy not found")
        else:
            raise HTTPException(status_code=400, detail="Either index or remove_all must be provided")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== User Management Endpoints ====================

@app.get("/api/v1/user/{user_id}", response_model=Dict[str, Any])
async def get_user_info(user_id: int, api_key: str = Depends(verify_api_key)):
    """
    Get user information
    """
    try:
        user = await ensure_user(user_id)
        is_premium = await is_premium_user(user_id)
        is_banned = await is_banned_user(user_id)
        
        # Get user's sites and proxies
        sites = await get_user_sites(user_id)
        proxies = await get_all_user_proxies(user_id)
        
        # Determine access type
        if is_banned:
            access = "banned"
        elif is_premium:
            access = "premium"
        else:
            access = "free"
        
        return {
            "success": True,
            "user_id": user_id,
            "is_premium": is_premium,
            "is_banned": is_banned,
            "access_type": access,
            "sites_count": len(sites),
            "proxies_count": len(proxies),
            "cc_limit": get_cc_limit(access, user_id)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/user/redeem", response_model=Dict[str, Any])
async def redeem_key(request: KeyRequest, api_key: str = Depends(verify_api_key)):
    """
    Redeem a premium key
    """
    try:
        await ensure_user(request.user_id)
        
        if await is_banned_user(request.user_id):
            raise HTTPException(status_code=403, detail="User is banned")
        
        if await is_premium_user(request.user_id):
            raise HTTPException(status_code=400, detail="User already has premium access")
        
        success, result = await use_key(request.user_id, request.key.upper())
        
        if not success:
            raise HTTPException(status_code=400, detail=result)
        
        return {
            "success": True,
            "message": f"Successfully redeemed {result} days of premium access"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== BIN Info Endpoint ====================

@app.get("/api/v1/bin/{card_number}", response_model=Dict[str, Any])
async def get_bin_info_endpoint(card_number: str, api_key: str = Depends(verify_api_key)):
    """
    Get BIN information for a credit card
    """
    try:
        brand, bin_type, level, bank, country, flag = await get_bin_info(card_number)
        
        return {
            "success": True,
            "card_number": card_number[:6] + "******" + card_number[-4:] if len(card_number) >= 10 else card_number,
            "bin": card_number[:6],
            "brand": brand,
            "type": bin_type,
            "level": level,
            "bank": bank,
            "country": country,
            "flag": flag
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== Admin Endpoints ====================

@app.post("/api/v1/admin/auth", response_model=Dict[str, Any])
async def admin_add_premium(request: AdminAuthRequest, api_key: str = Depends(verify_api_key)):
    """
    Grant premium access to a user (Admin only)
    """
    # You should implement admin verification here
    try:
        await ensure_user(request.user_id)
        await add_premium_user(request.user_id, request.days)
        
        return {
            "success": True,
            "user_id": request.user_id,
            "days": request.days,
            "message": f"Granted {request.days} days of premium access"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/admin/stats", response_model=Dict[str, Any])
async def get_bot_stats(api_key: str = Depends(verify_api_key)):
    """
    Get bot statistics (Admin only)
    """
    try:
        total_users = await get_total_users()
        total_premium = await get_premium_count()
        total_sites = await get_total_sites_count()
        users_with_sites = await get_users_with_sites()
        total_cards = await get_total_cards_count()
        charged_cards = await get_charged_count()
        approved_cards = await get_approved_count()
        
        all_keys = await get_all_keys()
        used_keys = len([k for k in all_keys if k.get('used', False)])
        
        return {
            "success": True,
            "users": {
                "total": total_users,
                "premium": total_premium,
                "free": total_users - total_premium
            },
            "sites": {
                "total": total_sites,
                "users_with_sites": users_with_sites
            },
            "cards": {
                "total_checked": total_cards,
                "charged": charged_cards,
                "approved": approved_cards
            },
            "keys": {
                "total_generated": len(all_keys),
                "used": used_keys,
                "unused": len(all_keys) - used_keys
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== Health Check ====================

@app.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

# ==================== Run Server ====================

if __name__ == "__main__":
    # Initialize database
    asyncio.run(init_db())
    
    # Run FastAPI server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
