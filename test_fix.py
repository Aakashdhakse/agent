"""Quick test to verify the orchestrator properly extracts user-mentioned data slots."""
import asyncio
from meta_agent.orchestrator import MetaOrchestrator


async def test():
    orch = MetaOrchestrator()
    analysis = orch._analyze_with_rules(
        "create a support bot for appointment booking take name email and greet that users",
        "en-US",
        "voiceowl"
    )
    print("=== User Requested Slots ===")
    print(analysis.get("user_requested_slots", []))
    print()
    print("=== Tasks ===")
    for t in analysis["tasks"]:
        print(f"  {t['task_name']}: collect={t.get('data_to_collect', [])}")
    print()
    print("=== Functions ===")
    for f in analysis["functions_needed"]:
        params = [p["name"] for p in f.get("input_params", [])]
        print(f"  {f['name']}: params={params}")
    print()
    print("=== Flow Summary ===")
    for step in analysis["flow_summary"]:
        print(f"  {step}")


asyncio.run(test())
