"""
Complete LangGraph SRE Validation System
========================================

This file contains the entire 6-agent LangGraph validation workflow.
All validation nodes, models, LLM service, and workflow logic in one file.

Usage:
    from sre_validation_system import validate_code_with_llm

    result = validate_code_with_llm(
        original_code="buggy code",
        fixed_code="fixed code",
        original_error="error message",
        change_context="what was changed"
    )

    print(f"Decision: {result['decision']}")
"""

import os
import json
import time
from typing import TypedDict, List, Literal, Optional
from dotenv import load_dotenv
import google.generativeai as genai
from langgraph.graph import StateGraph, START, END

# Load environment variables
load_dotenv()

# =============================================================================
# DATA MODELS
# =============================================================================

class SREValidationState(TypedDict):
    """State that flows through the LangGraph workflow"""
    # Input
    original_code: str
    fixed_code: str
    original_error: str
    change_context: str

    # Analysis Results
    error_analysis: Optional[dict]
    code_diff_analysis: Optional[dict]
    logic_validation: Optional[dict]
    semantic_validation: Optional[dict]
    security_validation: Optional[dict]

    # Final Decision
    decision: Optional[Literal["DEPLOY", "REJECT", "NEEDS_REVIEW"]]
    detailed_report: Optional[str]
    recommendations: Optional[List[str]]
    failure_reasons: Optional[List[str]]

# =============================================================================
# LLM SERVICE
# =============================================================================

class LLMService:
    """Service for interacting with Gemini AI"""

    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY","AIzaSyBZy2N1wvslhylOlsVsUphv4CBV3siyTx0")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is required")

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
            generation_config={
                "temperature": 0.1,
                "max_output_tokens": 4000,
            }
        )

    def invoke_with_json_response(self, prompt: str) -> dict:
        """Invoke LLM and parse JSON response with error handling and rate limiting"""
        max_retries = 3
        base_delay = 5  # seconds

        for attempt in range(max_retries):
            try:
                # # Add delay between requests to avoid rate limiting
                # if attempt > 0:
                #     delay = base_delay * (2 ** attempt)  # exponential backoff
                #     print(f"⏳ Rate limit delay: {delay}s (attempt {attempt + 1})")
                #     time.sleep(delay)

                response = self.model.generate_content(prompt)

                # Clean up response (remove markdown formatting if present)
                content = response.text.strip()
                if content.startswith("```json"):
                    content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

                # Extract just the JSON part (find first { to last })
                start = content.find('{')
                end = content.rfind('}') + 1
                if start != -1 and end > start:
                    content = content[start:end]

                # Parse JSON
                return json.loads(content)

            except Exception as e:
                error_msg = str(e).lower()

                # Handle rate limiting specifically
                if "429" in error_msg or "quota" in error_msg or "rate limit" in error_msg:
                    if attempt < max_retries - 1:
                        delay = 60  # Wait longer for rate limits
                        print(f"⚠️ Rate limit hit, waiting {delay}s before retry...")
                        time.sleep(delay)
                        continue
                    else:
                        print(f"❌ Rate limit exceeded after {max_retries} attempts")
                        return {
                            "error": "Rate limit exceeded",
                            "raw_response": "Rate limit error"
                        }

                # Handle JSON parsing errors
                if "json" in error_msg.lower():
                    print(f"JSON parsing error: {e}")
                    try:
                        print(f"Raw response: {content}")
                    except:
                        pass
                    return {
                        "error": "Failed to parse LLM response",
                        "raw_response": str(e)
                    }

                # Handle other errors
                print(f"LLM invocation error: {e}")
                if attempt < max_retries - 1:
                    continue
                else:
                    return {
                        "error": f"LLM call failed: {str(e)}"
                    }

# =============================================================================
# VALIDATION NODES (6 AI AGENTS)
# =============================================================================

def analyze_error_node(state: SREValidationState) -> SREValidationState:
    """Node 1: Deep analysis of the original error"""
    llm_service = LLMService()

    prompt = f"""
You are an expert SRE engineer. Analyze this error deeply and provide insights.

ORIGINAL ERROR: {state['original_error']}
ORIGINAL CODE: 
{state['original_code']}

Analyze the error and provide a JSON response with this exact structure:
{{
    "error_type": "syntax|logic|runtime|performance|security|integration",
    "severity": "critical|high|medium|low",
    "root_cause": "detailed explanation of what caused this error",
    "impact_scope": "local|module|system|global",
    "fix_complexity": "simple|moderate|complex",
    "error_category": "detailed categorization"
}}

Focus on understanding the root cause and impact scope.
"""

    try:
        analysis = llm_service.invoke_with_json_response(prompt)
        print(f"✅ Error Analysis Complete: {analysis.get('error_type', 'unknown')} error, {analysis.get('severity', 'unknown')} severity")

        # Display detailed analysis
        print(f"📋 Root Cause: {analysis.get('root_cause', 'Not specified')}")
        print(f"📊 Impact Scope: {analysis.get('impact_scope', 'Unknown')}")
        print(f"🔧 Fix Complexity: {analysis.get('fix_complexity', 'Unknown')}")

        return {"error_analysis": analysis}
    except Exception as e:
        print(f"❌ Error Analysis Failed: {e}")
        return {"error_analysis": {"error": str(e)}}

def code_diff_analysis_node(state: SREValidationState) -> SREValidationState:
    """Node 2: Analyze changes between original and fixed code"""
    llm_service = LLMService()

    prompt = f"""
You are a senior code reviewer. Analyze the differences between original and fixed code.

ORIGINAL CODE:
{state['original_code']}

FIXED CODE:
{state['fixed_code']}

CHANGE CONTEXT: {state['change_context']}
ERROR ANALYSIS: {state.get('error_analysis', {})}

Provide detailed analysis in this JSON format:
{{
    "lines_changed": 5,
    "change_type": "addition|deletion|modification|refactoring",
    "change_scope": "minimal|moderate|extensive",
    "change_quality": "poor|adequate|good|excellent",
    "addresses_root_cause": true,
    "introduces_new_risks": false,
    "code_clarity_impact": "improved|unchanged|degraded",
    "maintainability_impact": "improved|unchanged|degraded"
}}

Focus on whether the changes actually address the root cause of the error.
"""

    try:
        analysis = llm_service.invoke_with_json_response(prompt)
        print(f"✅ Code Diff Analysis Complete: {analysis.get('change_scope', 'unknown')} changes, {analysis.get('change_quality', 'unknown')} quality")

        # Display detailed diff analysis
        print(f"🔄 Change Type: {analysis.get('change_type', 'Unknown')}")
        print(f"🎯 Addresses Root Cause: {analysis.get('addresses_root_cause', 'Unknown')}")
        print(f"⚠️  New Risks: {analysis.get('introduces_new_risks', 'Unknown')}")
        print(f"📈 Maintainability: {analysis.get('maintainability_impact', 'Unknown')}")

        return {"code_diff_analysis": analysis}
    except Exception as e:
        print(f"❌ Code Diff Analysis Failed: {e}")
        return {"code_diff_analysis": {"error": str(e)}}

def logic_validation_node(state: SREValidationState) -> SREValidationState:
    """Node 3: Validate the logical correctness of the fix"""
    llm_service = LLMService()

    prompt = f"""
You are a software architect with 15+ years of experience. Validate the logical correctness of this fix.

ORIGINAL ERROR: {state['original_error']}
ERROR ANALYSIS: {state.get('error_analysis', {})}

ORIGINAL CODE:
{state['original_code']}

FIXED CODE:
{state['fixed_code']}

CODE DIFF ANALYSIS: {state.get('code_diff_analysis', {})}

Provide logical validation in this JSON format:
{{
    "logic_correctness": "correct|flawed|partially_correct",
    "addresses_original_error": true,
    "creates_new_logical_errors": false,
    "edge_cases_handled": true,
    "algorithm_soundness": "sound|questionable|flawed",
    "data_flow_correctness": "correct|incorrect|unknown",
    "control_flow_correctness": "correct|incorrect|unknown",
    "logical_reasoning": "detailed explanation of the logical assessment"
}}

Focus on whether the fix logically solves the problem without creating new issues.
"""

    try:
        analysis = llm_service.invoke_with_json_response(prompt)
        print(f"✅ Logic Validation Complete: {analysis.get('logic_correctness', 'unknown')}")

        # Display detailed logic analysis
        print(f"🎯 Solves Original Error: {analysis.get('addresses_original_error', 'Unknown')}")
        print(f"🔍 Edge Cases Handled: {analysis.get('edge_cases_handled', 'Unknown')}")
        print(f"⚖️  Algorithm Soundness: {analysis.get('algorithm_soundness', 'Unknown')}")
        if analysis.get('logical_reasoning'):
            print(f"💭 Reasoning: {analysis.get('logical_reasoning', '')[:150]}...")

        return {"logic_validation": analysis}
    except Exception as e:
        print(f"❌ Logic Validation Failed: {e}")
        return {"logic_validation": {"error": str(e)}}

def semantic_validation_node(state: SREValidationState) -> SREValidationState:
    """Node 4: Validate semantic correctness and best practices"""
    llm_service = LLMService()

    prompt = f"""
You are a principal engineer and code quality expert. Perform semantic analysis of this code fix.

FIXED CODE:
{state['fixed_code']}

CHANGE CONTEXT: {state['change_context']}
PREVIOUS ANALYSES: 
- Error: {state.get('error_analysis', {})}
- Logic: {state.get('logic_validation', {})}

Provide semantic validation in this JSON format:
{{
    "code_style_compliance": "excellent|good|acceptable|poor",
    "naming_conventions": "consistent|inconsistent|unclear",
    "code_organization": "well_structured|adequate|poor",
    "documentation_quality": "comprehensive|adequate|minimal|missing",
    "error_handling_quality": "robust|adequate|minimal|missing",
    "performance_implications": "improved|neutral|degraded|concerning",
    "maintainability_impact": "much_improved|improved|neutral|degraded",
    "follows_best_practices": true,
    "semantic_correctness": "correct|questionable|incorrect"
}}

Focus on code quality, maintainability, and adherence to best practices.
"""

    try:
        analysis = llm_service.invoke_with_json_response(prompt)
        print(f"✅ Semantic Validation Complete: {analysis.get('code_style_compliance', 'unknown')} style")

        # Display detailed semantic analysis
        print(f"📝 Naming Conventions: {analysis.get('naming_conventions', 'Unknown')}")
        print(f"🏗️  Code Organization: {analysis.get('code_organization', 'Unknown')}")
        print(f"🛡️  Error Handling: {analysis.get('error_handling_quality', 'Unknown')}")
        print(f"⚡ Performance Impact: {analysis.get('performance_implications', 'Unknown')}")
        print(f"✅ Best Practices: {analysis.get('follows_best_practices', 'Unknown')}")

        return {"semantic_validation": analysis}
    except Exception as e:
        print(f"❌ Semantic Validation Failed: {e}")
        return {"semantic_validation": {"error": str(e)}}

def security_validation_node(state: SREValidationState) -> SREValidationState:
    """Node 5: Security analysis of the code fix"""
    llm_service = LLMService()

    prompt = f"""
You are a cybersecurity expert specializing in secure code review. Analyze this code fix for security implications.

ORIGINAL CODE:
{state['original_code']}

FIXED CODE:
{state['fixed_code']}

ORIGINAL ERROR: {state['original_error']}
CHANGE CONTEXT: {state['change_context']}

Provide security analysis in this JSON format:
{{
    "vulnerabilities_found": ["list of security issues"],
    "security_improvements": true,
    "risk_level": "critical|high|medium|low|none",
    "input_validation_quality": "robust|adequate|weak|missing",
    "authentication_impact": "improved|unchanged|degraded",
    "data_exposure_risk": "high|medium|low|none",
    "security_recommendations": ["list of security recommendations"]
}}

Focus on identifying security vulnerabilities and validating that the fix doesn't introduce new security risks.
"""

    try:
        analysis = llm_service.invoke_with_json_response(prompt)
        print(f"✅ Security Validation Complete: {analysis.get('risk_level', 'unknown')} risk")

        # Display detailed security analysis
        vulnerabilities = analysis.get('vulnerabilities_found', [])
        if vulnerabilities:
            print(f"🚨 Vulnerabilities Found: {len(vulnerabilities)}")
            for i, vuln in enumerate(vulnerabilities[:2], 1):
                print(f"   {i}. {vuln}")

        print(f"🔒 Input Validation: {analysis.get('input_validation_quality', 'Unknown')}")
        print(f"🛡️  Security Improvements: {analysis.get('security_improvements', 'Unknown')}")

        recommendations = analysis.get('security_recommendations', [])
        if recommendations:
            print(f"💡 Security Recommendations: {len(recommendations)} items")
            for i, rec in enumerate(recommendations[:2], 1):
                print(f"   {i}. {rec[:100]}...")

        return {"security_validation": analysis}
    except Exception as e:
        print(f"❌ Security Validation Failed: {e}")
        return {"security_validation": {"error": str(e)}}

def final_decision_node(state: SREValidationState) -> SREValidationState:
    """Node 6: Make final deployment decision based on all validations"""
    llm_service = LLMService()

    prompt = f"""
You are the final decision maker for production deployments. Based on comprehensive analysis, make a deployment decision.

COMPREHENSIVE ANALYSIS RESULTS:
- Error Analysis: {state.get('error_analysis', {})}
- Code Diff Analysis: {state.get('code_diff_analysis', {})}
- Logic Validation: {state.get('logic_validation', {})}
- Semantic Validation: {state.get('semantic_validation', {})}
- Security Validation: {state.get('security_validation', {})}

ORIGINAL ERROR: {state['original_error']}
CHANGE CONTEXT: {state['change_context']}

Make a final deployment decision using this JSON format:
{{
    "decision": "DEPLOY|REJECT|NEEDS_REVIEW",
    "decision_reasoning": "detailed explanation for the decision",
    "deployment_risk": "low|medium|high|critical",
    "recommended_actions": ["list of recommended actions"],
    "critical_issues": ["list of critical issues that must be addressed"],
    "minor_improvements": ["list of minor improvements that could be made"],
    "overall_assessment": "comprehensive assessment of the fix quality"
}}

DECISION CRITERIA:
- DEPLOY: Fix is safe, correct, and ready for production
- REJECT: Fix has critical issues, security vulnerabilities, or doesn't solve the problem  
- NEEDS_REVIEW: Fix is complex, has minor issues, or requires human judgment

Be thorough but decisive. Focus on production safety and correctness.
"""

    try:
        decision = llm_service.invoke_with_json_response(prompt)

        # Extract and structure the final result
        final_decision = decision.get("decision", "NEEDS_REVIEW")
        reasoning = decision.get("decision_reasoning", "No reasoning provided")
        recommendations = decision.get("recommended_actions", []) + decision.get("minor_improvements", [])
        issues = decision.get("critical_issues", [])

        # Create detailed report
        detailed_report = f"""
SRE VALIDATION REPORT
====================

DECISION: {final_decision}
REASONING: {reasoning}

OVERALL ASSESSMENT: {decision.get('overall_assessment', 'No assessment provided')}
DEPLOYMENT RISK: {decision.get('deployment_risk', 'Unknown')}

ANALYSIS SUMMARY:
- Error Type: {state.get('error_analysis', {}).get('error_type', 'Unknown')}
- Error Severity: {state.get('error_analysis', {}).get('severity', 'Unknown')}
- Logic Correctness: {state.get('logic_validation', {}).get('logic_correctness', 'Unknown')}
- Security Risk: {state.get('security_validation', {}).get('risk_level', 'Unknown')}
- Code Quality: {state.get('semantic_validation', {}).get('code_style_compliance', 'Unknown')}
"""

        print(f"🎯 Final Decision: {final_decision}")

        # Display decision details
        print(f"🎯 Decision Reasoning: {reasoning[:200]}...")
        print(f"⚠️  Deployment Risk: {decision.get('deployment_risk', 'Unknown')}")

        if recommendations:
            print(f"📋 Recommendations: {len(recommendations)} items")
            for i, rec in enumerate(recommendations[:3], 1):
                print(f"   {i}. {rec}")

        if issues:
            print(f"🚨 Critical Issues: {len(issues)} found")
            for i, issue in enumerate(issues[:3], 1):
                print(f"   {i}. {issue}")

        return {
            "decision": final_decision,
            "detailed_report": detailed_report,
            "recommendations": recommendations,
            "failure_reasons": issues
        }

    except Exception as e:
        print(f"❌ Final Decision Failed: {e}")
        return {
            "decision": "REJECT",
            "detailed_report": f"Decision process failed: {str(e)}",
            "recommendations": ["Manual review required due to system failure"],
            "failure_reasons": [f"System error: {str(e)}"]
        }

# =============================================================================
# WORKFLOW ORCHESTRATION
# =============================================================================

def create_sre_validation_workflow():
    """
    Creates the main LangGraph workflow for SRE validation.

    WORKFLOW STEPS:
    1. Analyze original error (understand what went wrong)
    2. Analyze code differences (what changed)
    3. Validate logic (is the fix logically correct)
    4. Validate semantics (code quality, best practices)
    5. Validate security (security implications)
    6. Make final decision (DEPLOY/REJECT/NEEDS_REVIEW)
    """

    # Create the state graph
    workflow = StateGraph(SREValidationState)

    # Add all validation nodes
    workflow.add_node("analyze_error", analyze_error_node)
    workflow.add_node("analyze_code_diff", code_diff_analysis_node)
    workflow.add_node("validate_logic", logic_validation_node)
    workflow.add_node("validate_semantics", semantic_validation_node)
    workflow.add_node("validate_security", security_validation_node)
    workflow.add_node("make_decision", final_decision_node)

    # Define the sequential flow
    # Each step builds on the previous analysis
    workflow.add_edge(START, "analyze_error")
    workflow.add_edge("analyze_error", "analyze_code_diff")
    workflow.add_edge("analyze_code_diff", "validate_logic")
    workflow.add_edge("validate_logic", "validate_semantics")
    workflow.add_edge("validate_semantics", "validate_security")
    workflow.add_edge("validate_security", "make_decision")
    workflow.add_edge("make_decision", END)

    # Compile the workflow
    app = workflow.compile()

    print("🚀 SRE Validation Workflow Created Successfully!")
    print("📋 Workflow Steps: Error Analysis → Code Diff → Logic → Semantics → Security → Decision")

    return app

def validate_code_with_llm(original_code: str, fixed_code: str, original_error: str, change_context: str):
    """
    Main validation function - this replaces your Spring Boot validation logic.

    Args:
        original_code: The code that had the error
        fixed_code: The fixed/modified code
        original_error: Description of the original error
        change_context: Context about what was changed

    Returns:
        Complete validation result with decision
    """

    print("🎯 Starting LLM-Based SRE Validation...")
    print(f"📝 Original Error: {original_error[:100]}...")
    print(f"🔧 Change Context: {change_context}")

    # Create the workflow
    app = create_sre_validation_workflow()

    # Prepare initial state
    initial_state = {
        "original_code": original_code,
        "fixed_code": fixed_code,
        "original_error": original_error,
        "change_context": change_context
    }

    try:
        # Run the workflow - this is where the magic happens!
        print("⚡ Executing LangGraph Workflow...")
        result = app.invoke(initial_state)

        print(f"✅ Validation Complete! Decision: {result.get('decision', 'UNKNOWN')}")
        return result

    except Exception as e:
        print(f"❌ Workflow Execution Failed: {e}")
        return {
            "decision": "REJECT",
            "detailed_report": f"Workflow failed: {str(e)}",
            "recommendations": ["Manual review required due to system failure"],
            "failure_reasons": [f"System error: {str(e)}"]
        }
