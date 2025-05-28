# SYNGENTA_AI_AGENT/core/access_profiles.py

SIMULATED_USERS = {
    "analyst_us": {
        "name": "US Analyst",
        "role": "analyst",
        "region": "US",
        "permissions": [
            "view_sales_data", 
            "view_inventory_data", 
            "view_us_data_only" 
        ]
    },
    "manager_emea": {
        "name": "EMEA Manager",
        "role": "manager",
        "region": "EMEA",
        "permissions": [
            "view_sales_data", 
            "view_inventory_data", 
            "view_financial_metrics", 
            "view_emea_data_only" 
        ]
    },
    "guest_global": {
        "name": "Guest User",
        "role": "guest",
        "region": "GLOBAL", 
        "permissions": [
            "view_public_policies" 
        ]
    },
    "admin_global": {
        "name": "Global Admin",
        "role": "admin",
        "region": "GLOBAL",
        "permissions": [
            "view_sales_data", 
            "view_inventory_data", 
            "view_financial_metrics", 
            "view_all_regions", 
            "view_all_policies",
            "admin_override_all" 
        ]
    }
}

DEFAULT_USER_ID = "guest_global"

def get_user_profile(user_id: str) -> dict:
    if not user_id or not user_id.strip(): 
        return SIMULATED_USERS.get(DEFAULT_USER_ID, {})
    return SIMULATED_USERS.get(user_id, SIMULATED_USERS.get(DEFAULT_USER_ID, {}))