import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Add project root to sys.path
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from plugins.memory.cymru import CymruMemoryProvider

def test_integration():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    if not url or not key:
        print("SKIP: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not configured")
        return

    print("--- CYMRU Memory Provider Integration Test ---")
    provider = CymruMemoryProvider()
    
    # 1. Test availability
    print(f"Provider available: {provider.is_available()}")
    assert provider.is_available() == True
    
    # 2. Get a valid user_id from database
    import httpx
    client = httpx.Client(headers={
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    })
    
    resp = client.get(f"{url.rstrip('/')}/rest/v1/members?limit=1")
    user_id = None
    if resp.status_code == 200 and resp.json():
        user_id = resp.json()[0].get("user_id")
        print(f"Fetched test user_id: {user_id}")
    else:
        print("No user found in members table, using a mock UUID")
        user_id = "00000000-0000-0000-0000-000000000000"

    # 3. Initialize provider
    print("Initializing provider...")
    provider.initialize(
        session_id="test_session_123",
        user_id=user_id,
        agent_context="primary",
        agent_identity="coder"
    )

    # 4. Test system prompt block
    print("\n--- System Prompt Block ---")
    prompt = provider.system_prompt_block()
    print(prompt)
    print("---------------------------\n")

    # 5. Test prefetch/search
    print("Testing prefetch/hybrid search...")
    context = provider.prefetch("astrology minerals")
    print("\n--- Prefetch Context ---")
    print(context)
    print("------------------------\n")

    # 6. Test memory write
    if openai_key:
        print("Testing memory write mirroring...")
        provider.on_memory_write("add", "memory", "Antigravity is working on the standalone CYMRU database migration.")
        print("Memory write scheduled. Waiting 3 seconds for background thread...")
        import time
        time.sleep(3.0)
        print("Done.")
    else:
        print("SKIP: OPENAI_API_KEY not configured, skipping memory write mirroring test")

    provider.shutdown()
    print("SUCCESS: cymru memory provider integration test completed successfully.")

if __name__ == "__main__":
    test_integration()
