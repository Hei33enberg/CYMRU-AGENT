"""
Quick smoke-test for supabase_skills bridge.
Run: python bridges/test_bridge.py

Expected without real keys: EnvironmentError or auth error from Supabase.
Expected with real keys: prints list of god_skills rows.
"""
from bridges.supabase_skills import search_skills, get_skills_for_intent

if __name__ == "__main__":
    print("=== search_skills('shaman') ===")
    results = search_skills("shaman")
    for r in results:
        print(f"  [{r.get('id')}] {r.get('name')} (score={r.get('quality_score')})")

    print("=== get_skills_for_intent('translate') ===")
    results2 = get_skills_for_intent("translate")
    for r in results2:
        print(f"  [{r.get('id')}] {r.get('name')}")

    print("Done.")
