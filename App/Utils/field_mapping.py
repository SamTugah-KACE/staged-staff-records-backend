# utils/field_mapping.py

import json
import re
from typing import Dict, Any

# A mapping of normalized keys to canonical field names.
FIELD_SYNONYMS = {
    "title": "title",
    "prefix": "title",
    "prefixname": "title",
    "firstname": "first_name",
    "first name": "first_name",
    "first": "first_name",
    "givenname": "first_name",
    "given name": "first_name",
    "given": "first_name",
    "middlename": "middle_name",
    "middle name": "middle_name",
    "middle": "middle_name",
    "middleinitial": "middle_name",
    "middle initial": "middle_name",
    "surname": "last_name",
    "last": "last_name",
    "familyname": "last_name",
    "family name": "last_name",
    "family": "last_name",
    "lastname": "last_name",
    "last name": "last_name",
    "sex": "gender",  # UI might send "sex" while our backend expects "gender"
    "gender": "gender",
    "dob": "date_of_birth",
    "dateofbirth": "date_of_birth",
    "date of birth": "date_of_birth",
    "birthdate": "date_of_birth",
    "birth date": "date_of_birth",
    "date_of_birth": "date_of_birth",
    "maritalstatus": "marital_status",
    "marital status": "marital_status",
    "marital": "marital_status",
    "marital_status": "marital_status",
    "e-mail": "email",
    "emailaddress": "email",
    "email address": "email",
    "email": "email",
    "contact": "contact_info",
    "contactinfo": "contact_info",
    "phone": "contact_info",  # sometimes phone is sent instead of full contact_info
    "residential address": "address",
    "residentialaddress": "address",
    "residential": "address",
    "residential_address": "address",
    "address": "address",
    "postal address": "address",
    "postaladdress": "address",
    "postal": "address",
    "postal_code": "address",  # sometimes postal code is sent instead of full address
    "postalcode": "address",
    "home": "address",  # sometimes home is sent instead of full address
    "home_address": "address",
    "home address": "address",
    "homeaddress": "address",
    "personal address": "address",
    "personaladdress": "address",
    "personal": "address",
    "personal_address": "address",
    "employee type": "employee_type",
    "employee_type": "employee_type",
    "employment type": "employee_type",
    "employmenttype": "employee_type",
    "employment_type": "employee_type",
    "employment": "employee_type",
    "employee": "employee_type",
    "rank": "rank",
    "assigned rank": "rank",
    "assignedrank": "rank",
    "assigned_rank": "rank",
    "assigned department": "assigned_dept",  # may need to be mapped to department or similar
    "assigneddepartment": "assigned_dept",  # may need to be mapped to department or similar
    "assigned dept": "assigned_dept",  # may need to be mapped to department or similar
    "assigneddept": "assigned_dept",  # may need to be mapped to department or similar
    "department": "assigned_dept",     # if UI sends “department” we map to our standard field
    "role": "Role",  # for managerial assignment
    "academic qualifications": "academic_qualifications",
    "professional qualifications": "professional_qualifications",
    "payment details": "payment_details",
    "next of kin": "next_of_kin",
    "Submit Button": None,  # to be ignored
    "organization_id": "organization_id",  # allow exact matches too
}

def normalize_key(key: str) -> str:
    """Normalize a key by lowercasing, stripping extra spaces, and removing punctuation."""
    key = key.strip().lower()
    key = re.sub(r"[^\w\s]", "", key)
    return key

def map_employee_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remap dynamic UI keys (which may be synonyms) to the canonical backend field names.
    Any field not found in the mapping is retained (so extra data can later be merged).
    """
    mapped_data = {}
    for key, value in data.items():
        normalized = normalize_key(key)
        canonical = FIELD_SYNONYMS.get(normalized, key)
        mapped_data[canonical] = value
    return mapped_data


def merge_contact_info_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge any keys (from the mapped data) that indicate contact information into the 'contact_info' field.
    
    Specifically, if a key's normalized name contains 'phone' or 'address' and does not include "next of kin",
    then that key and its value are merged into data["contact_info"]. The existing value in 'contact_info'
    is parsed as a dict if needed.
    
    For example, keys like 'phone', 'residential address', 'employee address', and 'address' are appended
    into the contact_info dict.
    """
    # Initialize or parse existing contact_info.
    contact_info: Dict[str, Any] = {}
    if "contact_info" in data:
        if isinstance(data["contact_info"], str):
            try:
                contact_info = json.loads(data["contact_info"])
            except Exception:
                contact_info = {}
        elif isinstance(data["contact_info"], dict):
            contact_info = data["contact_info"]

    keys_to_remove = []
    for key, value in data.items():
        normalized = key.strip().lower()
        # If the key indicates contact details by containing 'phone' or 'address'
        # but exclude keys containing "next of kin"
        if ("phone" in normalized or "address" in normalized) and "next of kin" not in normalized:
            # Append the field to the contact_info dict.
            contact_info[key] = value
            keys_to_remove.append(key)
    
    # Remove merged keys from the main dictionary.
    for key in keys_to_remove:
        if key != "contact_info":  # Ensure we don't remove our own field
            data.pop(key, None)
    data["contact_info"] = contact_info
    return data