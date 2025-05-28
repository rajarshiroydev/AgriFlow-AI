import logging
from typing import Optional

# Use relative import if access_profiles is in the same 'core' package
from .access_profiles import get_user_profile 

logger = logging.getLogger(__name__)

SENSITIVE_QUERY_KEYWORDS = {
    "financial_metrics": ["profit", "margin", "revenue", "cost", "financial", "spend", "value", "salaries", "budget"],
    "detailed_customer_info": ["customer address", "customer contact", "customer email", "phone number"],
    "sensitive_policy_access": ["security audit results", "incident report details", "legal case files"]
}

PERMISSION_MAP = {
    "financial_metrics": "view_financial_metrics",
    "detailed_customer_info": "view_detailed_customer_data",
    "sensitive_policy_access": "view_sensitive_policies",
    "sales_data": "view_sales_data", # General sales data
    "inventory_data": "view_inventory_data" # General inventory data
}

def log_access_attempt(user_id: str, resource_type: str, query_text: str, allowed: bool):
    profile = get_user_profile(user_id)
    user_name = profile.get("name", user_id)
    status = "GRANTED" if allowed else "DENIED"
    logger.info(
        f"AUDIT LOG: User '{user_name}' (ID: {user_id}, Role: {profile.get('role', 'N/A')}, Region: {profile.get('region', 'N/A')}) "
        f"attempt to access '{resource_type}'. Query: '{query_text[:100]}...'. Access: {status}"
    )

def has_permission(user_id: str, required_permission: str) -> bool:
    profile = get_user_profile(user_id)
    user_permissions = profile.get("permissions", [])
    
    if "admin_override_all" in user_permissions:
        return True
    if required_permission in user_permissions:
        return True
    return False

def check_query_access(user_id: str, query_text: str, decomposed_db_question: Optional[str] = None, decomposed_doc_question: Optional[str] = None) -> bool:
    profile = get_user_profile(user_id)
    query_lower = query_text.lower()
    db_q_lower = decomposed_db_question.lower() if decomposed_db_question else ""
    doc_q_lower = decomposed_doc_question.lower() if decomposed_doc_question else ""
    combined_search_text = query_lower + " " + db_q_lower + " " + doc_q_lower

    # Check for sensitive keywords and required permissions
    for data_type, keywords in SENSITIVE_QUERY_KEYWORDS.items():
        permission_needed = PERMISSION_MAP.get(data_type)
        if not permission_needed:
            continue

        if any(keyword in combined_search_text for keyword in keywords):
            if not has_permission(user_id, permission_needed):
                log_access_attempt(user_id, data_type, query_text, allowed=False)
                logger.warning(f"Access DENIED for user '{user_id}' to sensitive data type '{data_type}' based on query: '{query_text}'")
                return False 
            else:
                # Log access to sensitive data even if permitted
                log_access_attempt(user_id, f"sensitive:{data_type}", query_text, allowed=True)

    # Example: General DB access check (guests might need a specific permission)
    if db_q_lower: # If there's any database question part
        if not has_permission(user_id, "view_sales_data") and not has_permission(user_id, "view_inventory_data") and not has_permission(user_id, "view_financial_metrics"):
            # If the user has none of the typical DB viewing permissions, and it's not covered by a more specific sensitive check above
            is_sensitive_db_query = False
            for data_type, keywords in SENSITIVE_QUERY_KEYWORDS.items():
                 if PERMISSION_MAP.get(data_type) and any(keyword in combined_search_text for keyword in keywords):
                    is_sensitive_db_query = True
                    break
            if not is_sensitive_db_query: # If it's a general DB query not caught by specific sensitive keywords
                log_access_attempt(user_id, "general_database_query", query_text, allowed=False)
                logger.warning(f"Access DENIED for user '{user_id}' to general database query due to lack of base DB permissions: '{query_text}'")
                return False
    
    log_access_attempt(user_id, "query_processed", query_text, allowed=True) # Log general processing if no specific denial
    return True