import json
import logging
from typing import Dict, Any, Tuple
from openai import OpenAI
import config
from validators.phone import normalize_bd_phone
from .database import save_qualified_lead, log_rejected_lead, log_validation_history

logger = logging.getLogger("ai_validator")

# Lazy-loaded Groq OpenAI client
_groq_client: OpenAI = None

def get_groq_client() -> OpenAI:
    global _groq_client
    if _groq_client is None:
        if not config.GROQ_CLOUD_API_KEY:
            raise ValueError("GROQ_CLOUD_API_KEY is not configured in .env")
        _groq_client = OpenAI(
            api_key=config.GROQ_CLOUD_API_KEY,
            base_url=config.GROQ_BASE_URL,
            timeout=15.0
        )
    return _groq_client

def rule_based_pre_validation(lead: Dict[str, Any]) -> Tuple[bool, str, list]:
    """
    Step 3 of workflow: Perform basic rule-based validation before calling AI.
    Rejects malformed, incomplete, or invalid data immediately without wasting API quota.
    """
    issues = []
    bname = lead.get("business_name") or lead.get("organization") or lead.get("name") or ""
    phone = lead.get("phone") or ""
    email = lead.get("email") or ""

    if not bname or bname.strip().lower() in ('n/a', 'none', 'unknown', 'contact', 'home'):
        issues.append("Missing business or person name")

    # Check for at least one viable contact channel (phone or email)
    has_phone = bool(phone and phone != "N/A")
    has_email = bool(email and email != "N/A" and "@" in email)

    if not has_phone and not has_email:
        issues.append("Neither phone nor email is available")

    # Validate Bangladesh phone format if phone is provided
    if has_phone:
        is_val, norm_phone, err = normalize_bd_phone(phone)
        if not is_val:
            issues.append(f"Invalid Bangladesh phone number format: {err}")
        else:
            lead["phone"] = norm_phone

    if issues:
        return False, "; ".join(issues), issues

    return True, "Passed rule-based checks", []

def validate_lead_with_ai(lead: Dict[str, Any], target_industry: str = "Hospitality & Tourism") -> Dict[str, Any]:
    """
    Validates a scraped lead using the Groq AI model with strict JSON output.
    Returns the parsed and verified validation result dictionary.
    """
    # 1. Rule-based pre-validation
    passed_rules, rule_reason, rule_issues = rule_based_pre_validation(lead)
    if not passed_rules:
        rejection_payload = {
            "is_valid": False,
            "confidence_score": 0,
            "business_name": lead.get("business_name") or lead.get("organization") or "N/A",
            "contact_person": lead.get("contact_person") or lead.get("name") or "N/A",
            "industry": target_industry,
            "reason": f"Rule-based rejection: {rule_reason}",
            "issues": rule_issues,
            "recommended_action": "reject",
            "rejection_stage": "rule_validation",
            "phone": lead.get("phone", "N/A"),
            "email": lead.get("email", "N/A"),
            "website": lead.get("website", "N/A"),
            "source_url": lead.get("source_url", "")
        }
        log_rejected_lead(rejection_payload)
        return rejection_payload

    # 2. Check if Groq API is configured
    if not config.has_groq_credentials():
        err_msg = "Groq Cloud API key is missing. Cannot perform required AI validation."
        logger.error(err_msg)
        rejection_payload = {
            "is_valid": False,
            "confidence_score": 0,
            "business_name": lead.get("business_name") or lead.get("organization") or "N/A",
            "contact_person": lead.get("contact_person") or lead.get("name") or "N/A",
            "industry": target_industry,
            "reason": err_msg,
            "issues": ["GROQ_CLOUD_API_KEY missing"],
            "recommended_action": "reject",
            "rejection_stage": "configuration_error",
            "phone": lead.get("phone", "N/A"),
            "email": lead.get("email", "N/A"),
            "website": lead.get("website", "N/A"),
            "source_url": lead.get("source_url", "")
        }
        log_rejected_lead(rejection_payload)
        return rejection_payload

    # 3. Formulate structured AI prompt
    bname = lead.get("business_name") or lead.get("organization") or "N/A"
    person = lead.get("contact_person") or lead.get("name") or "N/A"
    role = lead.get("designation") or "Executive"
    phone = lead.get("phone") or "N/A"
    email = lead.get("email") or "N/A"
    website = lead.get("website") or "N/A"
    address = lead.get("address") or lead.get("city") or "Bangladesh"
    source = lead.get("source_url") or "N/A"

    system_prompt = (
        "You are an expert AI Lead Validation Officer for Sunset Group (Sunset Kuakata Hotel & Resort).\n"
        "Your task is to strictly evaluate whether a scraped lead is a legitimate, relevant, and usable business prospect.\n\n"
        "Evaluation criteria:\n"
        "1. Is this a real business, organization, or decision-maker?\n"
        "2. Does it appear relevant to the target industry or corporate hospitality market?\n"
        "3. Is the collected contact information credible and usable?\n"
        "4. Is the phone number valid Bangladesh format (+880)?\n"
        "5. Is the website genuine or plausible?\n"
        "6. Is the information complete enough to be actionable?\n"
        "7. Is this a duplicate, spam entry, generic directory listing, or irrelevant result?\n\n"
        "CRITICAL RULES:\n"
        "- Do NOT invent or hallucinate missing information.\n"
        "- Output MUST be valid JSON adhering strictly to the schema:\n"
        "{\n"
        '  "is_valid": true,\n'
        '  "confidence_score": 92,\n'
        '  "business_name": "Example Business",\n'
        '  "industry": "Hospitality",\n'
        '  "reason": "Legitimate business with verified contact details.",\n'
        '  "issues": [],\n'
        '  "recommended_action": "accept"\n'
        "}\n"
        "- confidence_score must be an integer between 0 and 100.\n"
        "- recommended_action must be 'accept' or 'reject'."
    )

    user_prompt = (
        f"Target Industry: {target_industry}\n"
        f"Business/Organization: {bname}\n"
        f"Contact Person: {person}\n"
        f"Designation: {role}\n"
        f"Phone: {phone}\n"
        f"Email: {email}\n"
        f"Website: {website}\n"
        f"Address: {address}\n"
        f"Source URL: {source}\n\n"
        "Evaluate this prospect and respond with strict JSON."
    )

    try:
        client = get_groq_client()
        response = client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        raw_content = response.choices[0].message.content or "{}"
        parsed = json.loads(raw_content)

        # Normalize score
        raw_score = parsed.get("confidence_score", 0)
        if isinstance(raw_score, float) and raw_score <= 1.0:
            confidence_score = int(raw_score * 100)
        else:
            try:
                confidence_score = int(float(raw_score))
            except Exception:
                confidence_score = 0
        confidence_score = max(0, min(100, confidence_score))

        is_valid = bool(parsed.get("is_valid", False))
        recommended_action = str(parsed.get("recommended_action", "reject")).lower().strip()
        reason = str(parsed.get("reason", "No reason provided"))
        issues = parsed.get("issues", [])
        if not isinstance(issues, list):
            issues = [str(issues)]

        # Audit history log
        log_validation_history({
            "lead_identifier": f"{bname} | {person} | {phone}",
            "prompt_summary": f"Target: {target_industry} | URL: {source}",
            "raw_ai_response": raw_content,
            "is_valid": 1 if is_valid else 0,
            "confidence_score": confidence_score,
            "recommended_action": recommended_action
        })

        # Acceptance threshold: is_valid=True, recommended_action='accept', confidence_score >= 60
        if is_valid and recommended_action == "accept" and confidence_score >= 60:
            lead["ai_confidence_score"] = confidence_score
            lead["ai_validation_reason"] = reason
            lead["ai_recommended_action"] = "accept"
            
            # Save only qualified leads to database
            lead_id = save_qualified_lead(lead)
            lead["db_id"] = lead_id

            return {
                "is_valid": True,
                "confidence_score": confidence_score,
                "business_name": bname,
                "industry": parsed.get("industry") or target_industry,
                "reason": reason,
                "issues": issues,
                "recommended_action": "accept",
                "lead_id": lead_id
            }
        else:
            # Rejection
            rejection_payload = {
                "is_valid": False,
                "confidence_score": confidence_score,
                "business_name": bname,
                "contact_person": person,
                "industry": target_industry,
                "reason": reason if reason else "Failed AI confidence threshold",
                "issues": issues if issues else ["Confidence score below threshold or action is reject"],
                "recommended_action": "reject",
                "rejection_stage": "ai_validation",
                "phone": phone,
                "email": email,
                "website": website,
                "source_url": source
            }
            log_rejected_lead(rejection_payload)
            return rejection_payload

    except Exception as e:
        logger.error(f"Groq AI validation failed with exception: {e}")
        # Conservative uncertainty handling: NEVER auto-accept on AI failure
        rejection_payload = {
            "is_valid": False,
            "confidence_score": 0,
            "business_name": bname,
            "contact_person": person,
            "industry": target_industry,
            "reason": f"AI Validation Error: {str(e)}",
            "issues": [f"API Failure: {str(e)}"],
            "recommended_action": "reject",
            "rejection_stage": "ai_api_failure",
            "phone": phone,
            "email": email,
            "website": website,
            "source_url": source
        }
        log_rejected_lead(rejection_payload)
        return rejection_payload

