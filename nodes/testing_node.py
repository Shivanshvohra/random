from sre_validation_system import validate_code_with_llm
from typing import Dict
from google.api_core.exceptions import ResourceExhausted

def testing_node(state: Dict) -> Dict:
    print("🧪 [Testing Node] Starting full LLM-based SRE validation...")

    relevant_files = state["relevant_files"]
    original_code_backup = state["original_code_backup"]

    original_code = "\n\n".join(
        f"// FILE: {fname}\n{original_code_backup.get(fname, '')}"
        for fname in relevant_files
    )
    fixed_code = "\n\n".join(
        f"// FILE: {fname}\n{file_info['content']}"
        for fname, file_info in relevant_files.items()
    )

    try:
        result = validate_code_with_llm(
            original_code=original_code,
            fixed_code=fixed_code,
            original_error=state["original_error"],
            change_context="Gemini fix applied based on Spring Boot error.log"
        )
    except ResourceExhausted as e:
        print("🚫 Gemini API quota exceeded. Halting validation.")

        return {
            **state,
            "decision": "NEEDS_REVIEW",
            "detailed_report": "Gemini API quota exhausted. LLM validation could not proceed.",
            "recommendations": ["Wait for quota reset or use a different API key."],
            "failure_reasons": ["QuotaExceeded"],
            "retries": state.get("retries", 0),
            "test_failure_reason": "❌ LLM validation skipped due to Gemini quota exhaustion.\n\n" + str(e)
        }
    except Exception as e:
        print(f"❌ Unexpected LLM error: {e}")

        return {
            **state,
            "decision": "NEEDS_REVIEW",
            "detailed_report": f"LLM validation failed due to an unexpected error: {e}",
            "recommendations": ["Check logs for error details", "Retry after fixing the error"],
            "failure_reasons": ["UnexpectedError"],
            "retries": state.get("retries", 0),
            "test_failure_reason": f"❌ LLM validation failed due to: {e}"
        }

    # Build updated state based on decision
    updated_state = {
        **state,
        "decision": result.get("decision"),
        "detailed_report": result.get("detailed_report"),
        "recommendations": result.get("recommendations"),
        "failure_reasons": result.get("failure_reasons"),
        "retries": state.get("retries", 0)
    }

    if result.get("decision") == "REJECT":
        updated_state["retries"] += 1
        reasons = result.get("failure_reasons", [])
        summary = (
            "REJECTED. Reasons: " + "; ".join(reasons)
            if reasons else
            "REJECTED. No clear reason provided."
        )
        full_report = result.get("detailed_report", "")
        updated_state["test_failure_reason"] = summary + "\n\n--- FULL VALIDATION REPORT ---\n" + full_report

    return updated_state
