import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from hub.orchestrator import orchestrator

logger = logging.getLogger(__name__)

router = APIRouter()

@router.websocket("/api/hub/spoke")
async def hub_spoke_websocket(websocket: WebSocket, device_id: str = None):
    await websocket.accept()
    
    # If device_id is not in query params, generate a temporary one
    if not device_id:
        import uuid
        device_id = f"temp-spoke-{uuid.uuid4()}"
        
    await orchestrator.register_socket(device_id, websocket)
    logger.info(f"WebSocket connection established for device: {device_id}")

    try:
        while True:
            # Wait for frames from the spoke client
            data = await websocket.receive()
            
            # Check frame type
            if "text" in data:
                import json
                try:
                    msg = json.loads(data["text"])
                    v = msg.get("v")
                    msg_type = msg.get("type")
                    payload = msg.get("payload", {})
                    
                    # Update device_id if handshake/pairing provides a persistent one
                    msg_device_id = msg.get("device_id")
                    if msg_device_id and msg_device_id != device_id:
                        # Re-register under the persistent device_id
                        await orchestrator.deregister_socket(device_id)
                        device_id = msg_device_id
                        await orchestrator.register_socket(device_id, websocket)

                    if msg_type == "handshake":
                        response = await orchestrator.handle_handshake(device_id, payload)
                        await websocket.send_json(response)
                        
                    elif msg_type == "pairing":
                        response = await orchestrator.handle_pairing(device_id, payload)
                        await websocket.send_json(response)
                        
                    elif msg_type == "control":
                        await orchestrator.handle_control(device_id, payload)
                        
                    elif msg_type == "heartbeat":
                        await orchestrator.handle_heartbeat(device_id)
                        
                except Exception as e:
                    logger.error(f"Error handling text frame from {device_id}: {e}")
                    await websocket.send_json({
                        "v": 1,
                        "type": "error",
                        "device_id": device_id,
                        "payload": {"message": f"Server error: {str(e)}"}
                    })
                    
            elif "bytes" in data:
                audio_bytes = data["bytes"]
                await orchestrator.handle_audio_frame(device_id, audio_bytes)
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for device: {device_id}")
    except Exception as e:
        logger.error(f"Unexpected error in websocket loop for {device_id}: {e}")
    finally:
        await orchestrator.deregister_socket(device_id)
