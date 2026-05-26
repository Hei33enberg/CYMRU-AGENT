import os
import time
import random
import logging
from typing import Dict, Tuple, Any, Optional
from supabase import create_client, Client

logger = logging.getLogger(__name__)

# Supabase config
_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

def get_db_client() -> Client:
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        raise EnvironmentError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
    return create_client(_SUPABASE_URL, _SUPABASE_KEY)

class HubOrchestrator:
    def __init__(self):
        # Maps device_id -> active websocket connection
        self.active_sockets: Dict[str, Any] = {}
        # Maps device_id -> authenticated user_id
        self.device_users: Dict[str, str] = {}
        # Temporary pairing tokens: pairing_token -> (user_id, expires_at)
        self.pairing_tokens: Dict[str, Tuple[str, float]] = {}

    def generate_pairing_token(self, user_id: str, ttl: int = 600) -> str:
        """Generate a 6-digit pairing token that expires in `ttl` seconds."""
        token = f"{random.randint(100000, 999999)}"
        expires_at = time.time() + ttl
        self.pairing_tokens[token] = (user_id, expires_at)
        logger.info(f"Generated pairing token {token} for user {user_id}")
        return token

    def verify_pairing_token(self, token: str) -> Optional[str]:
        """Verify the token and return the associated user_id if valid/not expired."""
        if token not in self.pairing_tokens:
            return None
        user_id, expires_at = self.pairing_tokens[token]
        if time.time() > expires_at:
            del self.pairing_tokens[token]
            return None
        return user_id

    async def register_socket(self, device_id: str, websocket: Any):
        self.active_sockets[device_id] = websocket
        logger.info(f"Device socket registered: {device_id}")

    async def deregister_socket(self, device_id: str):
        if device_id in self.active_sockets:
            del self.active_sockets[device_id]
        if device_id in self.device_users:
            user_id = self.device_users[device_id]
            del self.device_users[device_id]
            # Set offline in DB
            try:
                db = get_db_client()
                db.table("user_devices").update({"online": False}).eq("device_id", device_id).execute()
            except Exception as e:
                logger.error(f"Failed to set device {device_id} offline: {e}")
        logger.info(f"Device socket deregistered: {device_id}")

    async def handle_handshake(self, device_id: str, payload: dict) -> dict:
        """Authenticate/Register device on handshake."""
        device_kind = payload.get("device_kind", "other")
        display_name = payload.get("display_name", "Unknown Spoke")
        caps = payload.get("capabilities", {})
        pairing_token = payload.get("pairing_token")

        db = get_db_client()
        user_id = None

        if pairing_token:
            user_id = self.verify_pairing_token(pairing_token)
            if not user_id:
                return {
                    "v": 1,
                    "type": "handshake_ack",
                    "device_id": device_id,
                    "payload": {"status": "error", "message": "Invalid or expired pairing token"}
                }
        else:
            # Look up device_id in DB
            try:
                res = db.table("user_devices").select("user_id").eq("id", device_id).execute()
                if res.data:
                    user_id = res.data[0]["user_id"]
            except Exception as e:
                # If table schema doesn't match or table not populated, fallback to temporary session
                logger.error(f"Error querying user_devices: {e}")

        # If we couldn't resolve user_id, it is unauthenticated
        if not user_id:
            return {
                "v": 1,
                "type": "handshake_ack",
                "device_id": device_id,
                "payload": {"status": "error", "message": "Device not paired. Use pairing flow."}
            }

        self.device_users[device_id] = user_id

        # Update or Insert device record in DB
        try:
            device_data = {
                "user_id": user_id,
                "device_kind": device_kind,
                "display_name": display_name,
                "has_microphone": caps.get("has_microphone", False),
                "has_speaker": caps.get("has_speaker", False),
                "has_display": caps.get("has_display", False),
                "has_ptt": caps.get("has_ptt", False),
                "has_biometric": caps.get("has_biometric", False),
                "online": True,
                "last_seen_at": "now()"
            }
            # Upsert
            db.table("user_devices").upsert(
                dict(id=device_id, **device_data)
            ).execute()
        except Exception as e:
            logger.error(f"Failed to upsert user_device: {e}")

        # Return handshake_ack
        return {
            "v": 1,
            "type": "handshake_ack",
            "device_id": device_id,
            "payload": {
                "status": "authenticated",
                "is_primary": True,
                "wake_word": "hej_boze",
                "hub_version": "1.0.0"
            }
        }

    async def handle_pairing(self, device_id: str, payload: dict) -> dict:
        """Explicit pairing request from unauthenticated spoke."""
        token = payload.get("pairing_token")
        user_id = self.verify_pairing_token(token)

        if not user_id:
            return {
                "v": 1,
                "type": "pairing_result",
                "device_id": device_id,
                "payload": {
                    "success": False,
                    "session_id": None,
                    "error_message": "Invalid or expired token"
                }
            }

        self.device_users[device_id] = user_id

        # Insert placeholder device record in DB
        try:
            db = get_db_client()
            db.table("user_devices").upsert({
                "id": device_id,
                "user_id": user_id,
                "device_kind": "other",
                "display_name": "New Paired Device",
                "online": True,
                "last_seen_at": "now()"
            }).execute()
        except Exception as e:
            logger.error(f"Failed to upsert paired device: {e}")

        return {
            "v": 1,
            "type": "pairing_result",
            "device_id": device_id,
            "payload": {
                "success": True,
                "session_id": f"session-{device_id[:8]}",
                "error_message": None
            }
        }

    async def handle_control(self, device_id: str, payload: dict):
        """Handle control messages from Spoke."""
        action = payload.get("action")
        user_id = self.device_users.get(device_id)
        if not user_id:
            logger.warning(f"Control message from unauthenticated device {device_id}")
            return

        db = get_db_client()

        if action == "route_audio":
            target_device_id = payload.get("target_device_id")
            logger.info(f"Routing audio for user {user_id} from {device_id} to {target_device_id}")
            # In a real setup, we would route downstream audio WebSocket packets to target_device_id
            
        elif action == "ptt_state":
            state = payload.get("state")
            logger.info(f"PTT state change on {device_id} for user {user_id}: {state}")
            
        elif action == "set_primary":
            is_primary = payload.get("is_primary", False)
            logger.info(f"Set primary status of {device_id} to {is_primary}")
            try:
                # Transakcja/Update: reset all other devices of user to not primary
                if is_primary:
                    db.table("user_devices").update({"is_primary": False}).eq("user_id", user_id).execute()
                db.table("user_devices").update({"is_primary": is_primary}).eq("id", device_id).execute()
            except Exception as e:
                logger.error(f"Failed to update primary device in DB: {e}")

    async def handle_heartbeat(self, device_id: str):
        """Update last seen status."""
        user_id = self.device_users.get(device_id)
        if user_id:
            try:
                db = get_db_client()
                db.table("user_devices").update({"last_seen_at": "now()", "online": True}).eq("id", device_id).execute()
            except Exception as e:
                logger.debug(f"Failed to update heartbeat in DB: {e}")

    async def broadcast_to_user_devices(self, user_id: str, message: dict):
        """Send a JSON message to all active sockets of a given user."""
        for device_id, ws in list(self.active_sockets.items()):
            if self.device_users.get(device_id) == user_id:
                try:
                    await ws.send_json(message)
                except Exception as e:
                    logger.error(f"Failed to send message to device {device_id}: {e}")

    async def handle_audio_frame(self, device_id: str, data: bytes):
        """Handle raw incoming binary audio data."""
        user_id = self.device_users.get(device_id)
        if not user_id:
            return
        
        # Log frame activity
        logger.debug(f"Received audio frame from {device_id} of size {len(data)}")
        # In full implementation, pipe this chunk to local wake-word, STT transcriber, or a queue.
        # For S20 smoke testing, we can echo the audio back or log.

# Global orchestrator instance
orchestrator = HubOrchestrator()
