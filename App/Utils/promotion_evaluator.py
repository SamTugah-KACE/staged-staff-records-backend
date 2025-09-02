# Utils/promotion_evaluator.py
from datetime import datetime

def evaluate_promotion_criteria(criteria: dict, employee) -> bool:
    """
    Evaluate if an employee is eligible for promotion based on dynamic JSON criteria.
    
    The criteria may look like:
    {
        "employee_types": {
            "Full Time": {"min_years_since_last_promotion": 3, "min_performance_rating": 4.5},
            "Part Time": {"min_years_since_last_promotion": 2, "min_performance_rating": 4.0},
            "Contractual": {"min_years_since_last_promotion": 1, "min_performance_rating": 3.5}
        }
    }
    
    If no 'employee_types' key exists, universal keys such as 'min_years_since_last_promotion' are used.
    """
    eligible = True

    # Determine applicable rules.
    if "employee_types" in criteria:
        emp_type = getattr(employee, "employee_type", None)
        rules = criteria["employee_types"].get(emp_type)
        if not rules:
            return False
    else:
        rules = criteria

    # Use last_promotion_date if available; otherwise, use hire_date.
    reference_date = getattr(employee, "last_promotion_date", None) or employee.hire_date
    if not reference_date:
        return False
    years_since = (datetime.utcnow().date() - reference_date).days / 365.25

    # Check minimum years requirement.
    key = "min_years_since_last_promotion" if "min_years_since_last_promotion" in rules else "min_years_of_service"
    if key in rules and years_since < rules[key]:
        eligible = False

    # Check performance rating.
    if "min_performance_rating" in rules:
        if not hasattr(employee, "performance_rating") or employee.performance_rating < rules["min_performance_rating"]:
            eligible = False

    return eligible

def is_birthday(employee) -> bool:
    """Return True if today is the employee's birthday."""
    if not employee.date_of_birth:
        return False
    today = datetime.utcnow().date()
    return (employee.date_of_birth.month == today.month) and (employee.date_of_birth.day == today.day)
