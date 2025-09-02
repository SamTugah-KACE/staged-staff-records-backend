import pandas as pd
import numpy as np
import random
import string
import re
from datetime import datetime
import io

# Explicitly import xlwt for XLS support
try:
    import xlwt
except ImportError:
    xlwt = None
    print("xlwt not installed. XLS files will fallback to XLSX.")

# =============================================================================
# Helper Functions for Column Normalization & Fuzzy Matching
# =============================================================================

# We use these helpers in our file generation to simulate slight variations.
def normalize_column_name(col_name: str) -> str:
    """Lowercase, trim, and remove non-alphanumeric characters (except spaces)."""
    col_name = col_name.strip().lower()
    col_name = re.sub(r'[^a-z0-9\s]', '', col_name)
    col_name = re.sub(r'\s+', ' ', col_name)
    return col_name

# Example Synonyms mapping for common fields (these help simulate "slightly aligned" files).
SYNONYMS_MAP = {
    "first_name": {"first name", "firstname", "first"},
    "middle_name": {"middle name", "middlename", "middle"},
    "last_name": {"last name", "lastname", "last"},
    "email": {"email", "e-mail", "mail"},
    "hire_date": {"hire date", "start date", "joining date"},
    "department": {"department", "dept", "division", "section"},
    "branch": {"branch", "location", "site"},
    "role": {"role", "position", "job role"},
    # Add additional synonyms as needed...
}

def get_flat_synonyms():
    flat = []
    for syns in SYNONYMS_MAP.values():
        for s in syns:
            flat.append(normalize_column_name(s))
    return flat

FLAT_SYNONYMS = get_flat_synonyms()

def fuzzy_match_column(col_name: str, threshold: int = 80) -> str:
    """
    Uses RapidFuzz to try to find a match from FLAT_SYNONYMS.
    If a match with score>=threshold is found, returns the standardized concept
    (the key from SYNONYMS_MAP that contains the matched synonym).
    Otherwise, returns the normalized column name.
    """
    try:
        from rapidfuzz import process, fuzz
    except ImportError:
        raise ImportError("RapidFuzz must be installed: pip install rapidfuzz")
    
    normalized = normalize_column_name(col_name)
    best_match, score, _ = process.extractOne(normalized, FLAT_SYNONYMS, scorer=fuzz.ratio)
    if score >= threshold:
        for concept, syns in SYNONYMS_MAP.items():
            norm_syns = {normalize_column_name(s) for s in syns}
            if best_match in norm_syns:
                return concept
    return normalized

# =============================================================================
# File Generators
# =============================================================================

def generate_exact_excel_file(filename="exact_staff_records.xlsx", num_rows=100):
    """
    Generate an Excel file with multiple sheets exactly aligned with the project's models.
    Sheet names:
      - "Employees"
      - "AcademicQualifications"
      - "ProfessionalQualifications"
      - "EmploymentHistory"
      - "EmergencyContacts"
      - "NextOfKin"
    Column names exactly match the model field names.
    """
    # Employees Sheet
    df_emp = pd.DataFrame({
        "first_name": np.random.choice(["Alice", "Bob", "Carol", "Dave"], num_rows),
        "middle_name": np.random.choice(["", "J.", "K."], num_rows),
        "last_name": np.random.choice(["Smith", "Johnson", "Williams", "Brown"], num_rows),
        "email": [f"user{i}@example.com" for i in range(num_rows)],
        "hire_date": pd.date_range(start="2020-01-01", periods=num_rows, freq="D").strftime("%Y-%m-%d"),
        "department": np.random.choice(["HR", "IT", "Finance", "Marketing"], num_rows),
        "branch": np.random.choice(["Head Quarters", "Legon", "Kasoa", "Adum - Kumasi"], num_rows),
        "role": np.random.choice(["Manager", "Staff"], num_rows),
        "salary": np.random.randint(30000, 100000, num_rows)
    })

    # Academic Qualifications Sheet
    df_acad = pd.DataFrame({
        "degree": np.random.choice(["BSc", "MSc", "PhD"], num_rows),
        "institution": np.random.choice(["University A", "University B", "University C"], num_rows),
        "year_obtained": np.random.randint(1990, 2020, num_rows)
    })

    # Professional Qualifications Sheet
    df_prof = pd.DataFrame({
        "qualification_name": np.random.choice(["Certification A", "Certification B"], num_rows),
        "institution": np.random.choice(["Institute X", "Institute Y"], num_rows),
        "year_obtained": np.random.randint(2000, 2020, num_rows)
    })

    # Employment History Sheet
    df_emp_hist = pd.DataFrame({
        "job_title": np.random.choice(["Developer", "Analyst", "Manager"], num_rows),
        "company": np.random.choice(["Company A", "Company B"], num_rows),
        "start_date": pd.date_range(start="2015-01-01", periods=num_rows, freq="ME").strftime("%Y-%m-%d"),
        "end_date": pd.date_range(start="2016-01-01", periods=num_rows, freq="ME").strftime("%Y-%m-%d")
    })

    # Emergency Contacts Sheet
    df_emerg = pd.DataFrame({
        "name": np.random.choice(["John Doe", "Jane Roe"], num_rows),
        "relation": np.random.choice(["Parent", "Sibling"], num_rows),
        "phone": [f"0{random.randint(100000000, 999999999)}" for _ in range(num_rows)],
        "address": np.random.choice(["Address 1", "Address 2"], num_rows)
    })

    # Next of Kin Sheet
    df_nok = pd.DataFrame({
        "name": np.random.choice(["Jim Beam", "Jack Daniels"], num_rows),
        "relation": np.random.choice(["Spouse", "Sibling"], num_rows),
        "phone": [f"0{random.randint(100000000, 999999999)}" for _ in range(num_rows)],
        "address": np.random.choice(["Address 3", "Address 4"], num_rows)
    })

    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        df_emp.to_excel(writer, sheet_name="Employees", index=False)
        df_acad.to_excel(writer, sheet_name="AcademicQualifications", index=False)
        df_prof.to_excel(writer, sheet_name="ProfessionalQualifications", index=False)
        df_emp_hist.to_excel(writer, sheet_name="EmploymentHistory", index=False)
        df_emerg.to_excel(writer, sheet_name="EmergencyContacts", index=False)
        df_nok.to_excel(writer, sheet_name="NextOfKin", index=False)

    print(f"Exact Excel file generated: {filename}")


def generate_sample_excel_file(filename="sample_staff_records.xlsx", num_rows=100):
    """
    Generate a sample Excel file with multiple sheets but empty rows."""
    df_emp = pd.DataFrame({
        "first_name": [""] * num_rows,
        "middle_name": [""] * num_rows,
        "last_name": [""] * num_rows,
        "email": [""] * num_rows,
        "hire_date": [""] * num_rows,
        "department": [""] * num_rows,
        "branch": [""] * num_rows,
        "role": [""] * num_rows,
        "salary": [""] * num_rows
    })

    df_acad = pd.DataFrame({
        "degree": [""] * num_rows,
        "institution": [""] * num_rows,
        "year_obtained": [""] * num_rows,
        "email": [""] * num_rows,
    })

    df_prof = pd.DataFrame({
        "qualification_name": [""] * num_rows,
        "institution": [""] * num_rows,
        "year_obtained": [""] * num_rows,
        "email": [""] * num_rows,
    })

    df_emp_hist = pd.DataFrame({    
        "job_title": [""] * num_rows,
        "company": [""] * num_rows,
        "start_date": [""] * num_rows,
        "end_date": [""] * num_rows,
        "email": [""] * num_rows,
    })

    df_emerg = pd.DataFrame({
        "name": [""] * num_rows,
        "relation": [""] * num_rows,
        "phone": [""] * num_rows,
        "address": [""] * num_rows,
        "email": [""] * num_rows,
    })

    df_nok = pd.DataFrame({
        "name": [""] * num_rows,
        "relation": [""] * num_rows,
        "phone": [""] * num_rows,
        "address": [""] * num_rows,
        "email": [""] * num_rows,
    })

    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        df_emp.to_excel(writer, sheet_name="Employees", index=False)
        df_acad.to_excel(writer, sheet_name="AcademicQualifications", index=False)
        df_prof.to_excel(writer, sheet_name="ProfessionalQualifications", index=False)
        df_emp_hist.to_excel(writer, sheet_name="EmploymentHistory", index=False)
        df_emerg.to_excel(writer, sheet_name="EmergencyContacts", index=False)
        df_nok.to_excel(writer, sheet_name="NextOfKin", index=False)
        

    print(f"Sample Excel file generated: {filename}")



def generate_slightly_aligned_excel_file(filename="slightly_aligned_staff_records.xlsx", num_rows=100):
    """
    Generate an Excel file with multiple sheets whose column names are similar but not exact.
    For example, 'first name' instead of 'first_name', 'dept' instead of 'department', etc.
    """
    df_emp = pd.DataFrame({
        "First Name": np.random.choice(["Alice", "Bob", "Carol", "Dave"], num_rows),
        "Middle": np.random.choice(["", "J.", "K."], num_rows),
        "Last Name": np.random.choice(["Smith", "Johnson", "Williams", "Brown"], num_rows),
        "E-mail": [f"user{i}@example.com" for i in range(num_rows)],
        "Start Date": pd.date_range(start="2020-01-01", periods=num_rows, freq="D").strftime("%Y-%m-%d"),
        "Dept": np.random.choice(["HR", "IT", "Finance", "Marketing"], num_rows),
        "Site": np.random.choice(["Head Quarters", "Legon", "Kasoa", "Adum - Kumasi"], num_rows),
        "Position": np.random.choice(["Manager", "Staff"], num_rows),
        "Salary": np.random.randint(30000, 100000, num_rows)
    })

    # A second sheet with academic data using slightly different column names.
    df_acad = pd.DataFrame({
        "Degree": np.random.choice(["BSc", "MSc", "PhD"], num_rows),
        "Institution Name": np.random.choice(["University A", "University B", "University C"], num_rows),
        "Year": np.random.randint(1990, 2020, num_rows)
    })

    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        df_emp.to_excel(writer, sheet_name="StaffData", index=False)
        df_acad.to_excel(writer, sheet_name="Academics", index=False)

    print(f"Slightly aligned Excel file generated: {filename}")

def generate_single_sheet_excel_file(filename="single_sheet_staff_records.xlsx", num_rows=100):
    """
    Generate an Excel file with a single sheet containing all fields for every model.
    The single sheet includes columns for employee bio, academic, professional, employment,
    emergency contact, and next-of-kin data.
    """
    # Define columns for each model. In production, these should match the exact expected field names.
    employee_cols = ["first_name", "middle_name", "last_name", "email", "hire_date", "department", "branch", "role", "salary"]
    academic_cols = ["degree", "institution", "year_obtained"]
    professional_cols = ["qualification_name", "institution", "year_obtained"]
    employment_cols = ["job_title", "company", "start_date", "end_date"]
    emergency_cols = ["contact_name", "relation", "phone", "address"]
    nok_cols = ["nok_name", "relation", "phone", "address"]

    all_cols = employee_cols + academic_cols + professional_cols + employment_cols + emergency_cols + nok_cols

    # Create random data for each column.
    data = {
        "first_name": np.random.choice(["Alice", "Bob", "Carol", "Dave"], num_rows),
        "middle_name": np.random.choice(["", "J.", "K."], num_rows),
        "last_name": np.random.choice(["Smith", "Johnson", "Williams", "Brown"], num_rows),
        "email": [f"user{i}@example.com" for i in range(num_rows)],
        "hire_date": pd.date_range(start="2020-01-01", periods=num_rows, freq="D").strftime("%Y-%m-%d"),
        "department": np.random.choice(["HR", "IT", "Finance", "Marketing"], num_rows),
        "branch": np.random.choice(["Head Quarters", "Legon", "Kasoa", "Adum - Kumasi"], num_rows),
        "role": np.random.choice(["Manager", "Staff"], num_rows),
        "salary": np.random.randint(30000, 100000, num_rows),
        "degree": np.random.choice(["BSc", "MSc", "PhD"], num_rows),
        "institution": np.random.choice(["University A", "University B", "University C"], num_rows),
        "year_obtained": np.random.randint(1990, 2020, num_rows),
        "qualification_name": np.random.choice(["Cert A", "Cert B"], num_rows),
        "company": np.random.choice(["Company A", "Company B"], num_rows),
        "job_title": np.random.choice(["Developer", "Analyst", "Manager"], num_rows),
        "start_date": pd.date_range(start="2015-01-01", periods=num_rows, freq="ME").strftime("%Y-%m-%d"),
        "end_date": pd.date_range(start="2016-01-01", periods=num_rows, freq="ME").strftime("%Y-%m-%d"),
        "contact_name": np.random.choice(["John Doe", "Jane Roe"], num_rows),
        "relation": np.random.choice(["Parent", "Sibling"], num_rows),
        "phone": [f"0{random.randint(100000000, 999999999)}" for _ in range(num_rows)],
        "address": np.random.choice(["Address 1", "Address 2"], num_rows),
        "nok_name": np.random.choice(["Jim Beam", "Jack Daniels"], num_rows)
    }

    df_all = pd.DataFrame(data, columns=all_cols)
    
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        df_all.to_excel(writer, sheet_name="AllStaffData", index=False)
    
    print(f"Single-sheet Excel file generated: {filename}")

def generate_generic_excel_file(filename="generic_staff_records.xlsx", num_rows=100):
    """
    Generate an Excel file that follows an international standardized format.
    This file has multiple sheets with generic column names that are expected in many HR systems.
    For example, one sheet for personal data, one for work details, one for education, etc.
    """
    # Personal Data
    df_personal = pd.DataFrame({
        "Given Name": np.random.choice(["Alice", "Bob", "Carol", "Dave"], num_rows),
        "Family Name": np.random.choice(["Smith", "Johnson", "Williams", "Brown"], num_rows),
        "Date of Birth": pd.date_range(start="1970-01-01", periods=num_rows, freq="YE").strftime("%Y-%m-%d"),
        "Email Address": [f"user{i}@example.com" for i in range(num_rows)]
    })
    
    # Work Details
    df_work = pd.DataFrame({
        "Hire Date": pd.date_range(start="2020-01-01", periods=num_rows, freq="D").strftime("%Y-%m-%d"),
        "Department": np.random.choice(["HR", "IT", "Finance", "Marketing"], num_rows),
        "Job Title": np.random.choice(["Manager", "Staff", "Developer"], num_rows),
        "Office Location": np.random.choice(["Head Quarters", "Branch A", "Branch B"], num_rows)
    })
    
    # Education
    df_education = pd.DataFrame({
        "Highest Degree": np.random.choice(["BSc", "MSc", "PhD"], num_rows),
        "Institution": np.random.choice(["University X", "University Y"], num_rows),
        "Graduation Year": np.random.randint(1990, 2020, num_rows)
    })
    
    # Additional Generic Data (e.g., address, phone)
    df_generic = pd.DataFrame({
        "Residential Address": np.random.choice(["123 Main St", "456 Oak Ave"], num_rows),
        "Contact Number": [f"0{random.randint(100000000, 999999999)}" for _ in range(num_rows)]
    })
    
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        df_personal.to_excel(writer, sheet_name="Personal", index=False)
        df_work.to_excel(writer, sheet_name="Work", index=False)
        df_education.to_excel(writer, sheet_name="Education", index=False)
        df_generic.to_excel(writer, sheet_name="Additional", index=False)
    
    print(f"Generic Excel file generated: {filename}")

# =============================================================================
# Main Execution Block
# =============================================================================
if __name__ == "__main__":
    # Generate each type of file:
    generate_sample_excel_file()
    # generate_exact_excel_file()
    # generate_slightly_aligned_excel_file()
    # generate_single_sheet_excel_file()
    # generate_generic_excel_file()
