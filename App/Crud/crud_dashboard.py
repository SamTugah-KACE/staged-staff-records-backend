# crud_dashboard.py
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from uuid import UUID

from Models.models import Dashboard
from Schemas.schemas import DashboardCreateSchema


# form_compiler.py
from typing import List, Dict


def compileDynamicSubmitCode(form_fields: List[Dict], apiUrl: str) -> str:
    """
    Generates a complete JavaScript submit function string based on the provided form_fields.
    
    The generated code includes:
      - Required field checks.
      - Field-type validations (e.g. phone, email).
      - Conditional submission: if any field contains file(s) then the code builds a FormData object; 
        otherwise, it submits JSON.
      - Uses the provided apiUrl as the endpoint.
    
    Parameters:
      form_fields (List[Dict]): An array of field definitions. Each field should have keys like:
          'id', 'required', and optionally 'validation' (e.g., for 'phone', 'email').
      apiUrl (str): The backend API URL to be used for form submission.
    
    Returns:
      str: A JavaScript code string representing the submit function.
    """
    validationLines = []
    
    # Loop over each field to build validations.
    for field in form_fields:
        fid = field.get("id")
        required = field.get("required", False)
        valConfig = field.get("validation", {})

        if required:
            # Validate that the field has a non-empty trimmed value.
            validationLines.append(f"""
                if (!formData['{fid}'] || formData['{fid}'].trim() === "") {{
                    throw new Error("The field '{fid}' is required.");
                }}
            """)

        if fid == "phone":
            maxLen = valConfig.get("maxLength", 10)
            validationLines.append(f"""
                if (formData['{fid}'] && !/^[0-9]{{{maxLen}}}$/.test(formData['{fid}'])) {{
                    throw new Error("Invalid phone number format. Must be {maxLen} digits.");
                }}
            """)

        if fid == "email":
            validationLines.append(f"""
                if (formData['{fid}'] && !/^[\\w-.]+@([\\w-]+\\.)+[\\w-]{{2,4}}$/.test(formData['{fid}'])) {{
                    throw new Error("Invalid email address.");
                }}
            """)

        # Additional field type validations can be added in similar fashion.

    validationsJS = "\n".join(validationLines)

    # Build the complete submit function.
    # Note: We use a conditional branch to check for file uploads by testing if any value in formData is an instance of File or FileList.
    compiledJS = f"""
        // Precompiled dynamic submit function.
        async function submitForm(formData) {{
            try {{
                // Check if at least one field holds a file.
                const hasFile = Object.values(formData).some(value => 
                  value instanceof File || (value instanceof FileList && value.length > 0)
                );
                if (hasFile) {{
                    // Build FormData for multipart submission.
                    const multipartData = new FormData();
                    for (const key in formData) {{
                        const value = formData[key];
                        if (value instanceof FileList) {{
                            for (let i = 0; i < value.length; i++) {{
                                multipartData.append(key, value[i]);
                            }}
                        }} else {{
                            multipartData.append(key, value);
                        }}
                    }}
                    const res = await fetch("{apiUrl}", {{
                        method: "POST",
                        headers: {{
                          "Authorization": "Bearer " + localStorage.getItem("token")
                        }},
                        body: multipartData
                    }});
                    if (!res.ok) throw new Error("Submission failed.");
                    alert("Form submitted successfully!");
                }} else {{
                    // Execute validations.
                    {validationsJS}
                    // Submit form as JSON.
                    const res = await fetch("{apiUrl}", {{
                        method: "POST",
                        headers: {{
                            "Content-Type": "application/json",
                            "Authorization": "Bearer " + localStorage.getItem("token")
                        }},
                        body: JSON.stringify(formData)
                    }});
                    if (!res.ok) throw new Error("Submission failed.");
                    alert("Form submitted successfully!");
                }}
            }} catch (error) {{
                console.error(error);
                alert(error.message);
            }}
        }}
    """
    return compiledJS


def create_dashboard(db: Session, dashboard_in: dict) -> Dashboard:
    """
    Create a new dashboard record for the given organization.
    """
    new_dashboard = Dashboard(**dashboard_in.dict())
    db.add(new_dashboard)
    db.commit()
    db.refresh(new_dashboard)
    return new_dashboard

def update_dashboard(db: Session, dashboard_id: UUID, updated_data: dict) -> Dashboard:
    """
    Update an existing dashboard record with partial or full changes.
    """
    dashboard = db.query(Dashboard).filter(Dashboard.id == dashboard_id).first()
    if not dashboard:
        raise ValueError("Dashboard not found")
    for key, value in updated_data.items():
        setattr(dashboard, key, value)
    db.commit()
    db.refresh(dashboard)
    return dashboard

def get_dashboards_by_org(db: Session, organization_id: UUID):
    """
    Retrieve all dashboards for the specified organization.
    """
    dashboards = db.query(Dashboard).filter(
        Dashboard.organization_id == organization_id
    ).all()
    return dashboards

def get_dashboard_by_id(db: Session, dashboard_id: UUID) -> Dashboard:
    """
    Retrieve a specific dashboard by its ID.
    """
    dashboard = db.query(Dashboard).filter(Dashboard.id == dashboard_id).first()
    if not dashboard:
        raise ValueError("Dashboard not found")
    return dashboard

def get_dashboard_by_user_org(db: Session, user_id: UUID, organization_id: UUID):
    """
    Retrieve a dashboard for the given user within the specified organization.
    Returns a single dashboard or None if not found.
    """
    return db.query(Dashboard).filter(
        Dashboard.user_id == user_id,
        Dashboard.organization_id == organization_id
    ).first()
