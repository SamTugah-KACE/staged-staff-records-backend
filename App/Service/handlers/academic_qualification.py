# src/services/handlers/academic_qualificatiin.py
from Service.data_input_handlers import register_handler

@register_handler("academic_qualifications")
def handle_academic_qualification(db, record):
    from Models.models import AcademicQualification
    emp = db.query(AcademicQualification).get(record.employee_id)
    for k, v in record.data.items():
        setattr(emp, k, v)
    db.add(emp)
    db.commit()
