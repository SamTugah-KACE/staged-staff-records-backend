# src/services/handlers/emp_handler.py
import logging
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import and_, inspect
from sqlalchemy.orm import Session
from Service.data_input_handlers import register_handler
from Models.models import AcademicQualification
from Models.models import ProfessionalQualification
from Models.models import EmploymentHistory
from Models.models import EmergencyContact
from Models.models import NextOfKin
from Models.models import PromotionRequest
from Models.models import Employee
from Models.models import EmployeePaymentDetail

logger = logging.getLogger(__name__)



# def _upsert_intelligent(db: Session, model, data: dict):
#     """
#     Upsert that:
#       1. Filters out any data keys not matching real columns,
#       2. Finds existing by PK (assumes single-column PK named 'id'),
#       3. If exists, updates only overlapping columns,
#       4. Otherwise instantiates with filtered data and adds it.
#     """
#     # 1️⃣ Determine valid column names
#     mapper = inspect(model)
#     valid_columns = {col.name for col in mapper.columns}

#     # 2️⃣ Filter incoming payload
#     filtered = {k: v for k, v in data.items() if k in valid_columns}

#     # 3️⃣ Identify PK name (assume single PK)
#     pk_cols = mapper.primary_key
#     if len(pk_cols) != 1:
#         raise RuntimeError(f"{model.__name__} uses composite PKs; not supported")
#     pk_name = pk_cols[0].name

#     # 4️⃣ Try to load existing
#     existing = None
#     if pk_name in filtered:
#         existing = db.get(model, filtered[pk_name])

#     if existing:
#         # 5️⃣ Update only those attributes the payload provided
#         for key, val in filtered.items():
#             setattr(existing, key, val)
#         return existing

#     # 6️⃣ Insert new
#     new_obj = model(**filtered)
#     db.add(new_obj)
#     return new_obj


def _upsert_biodata(
    db: Session,
    model,
    data: dict,
    request_type: str
):
    """
    data: raw payload dict
    request_type: "save" → always create new,
                  "update" → update existing if found, else insert.
    """
    # 1️⃣ Inspect valid columns and PK
    mapper       = inspect(model)
    valid_cols   = {col.name for col in mapper.columns}
    pk_cols      = mapper.primary_key
    if len(pk_cols) != 1:
        raise RuntimeError(f"{model.__name__} composite PK not supported")
    pk_name      = pk_cols[0].name

    # 2️⃣ Filter payload to actual columns
    payload = {k: v for k, v in data.items() if k in valid_cols}

    # 3️⃣ Look for existing if update
    existing = None
    if request_type == "update" and pk_name in payload:
        existing = db.get(model, payload[pk_name])

    print("_upsert intelligent:: ", request_type)
    print("existing:: ", existing)
    # 4️⃣ Decision tree
    if request_type == "save" or (request_type == "update" and existing is None):
        # Force a new insert
        # Remove PK so SQLAlchemy will generate one (if using autonumber/uuid default)
        payload.pop(pk_name, None)
        new_obj = model(**payload)
        db.add(new_obj)
        return new_obj

    print("payload to be patched:: ", payload)
    # 5️⃣ request_type==update and existing found → patch
    for key, val in payload.items():
        print(f"patching {model} as {key}: {val}")
        setattr(existing, key, val)
    return existing

def _set_nested_id(d: dict, new_id):
    """
    Recursively replace any 'id': '' entries with the real new_id.
    """
    if not isinstance(d, dict):
        return
    for k, v in d.items():
        if k == "id" and (v is None or v == ""):
            d[k] = new_id
        elif isinstance(v, dict):
            _set_nested_id(v, new_id)

def _find_nested_id(d: dict):
    """
    Recursively search d for any nested {'id': <value>} and return the first one found.
    """
    if not isinstance(d, dict):
        return None
    if "id" in d:
        return d["id"]
    for v in d.values():
        if isinstance(v, dict):
            found = _find_nested_id(v)
            if found is not None:
                return found
    return None

def _upsert_intelligent(
    db: Session,
    model,
    data: dict,
    request_type: str,
    lookup_fields: list[str] = None
):
    """
    1. Extract any nested `id` and promote it.
    2. Filter to real columns.
    3. request_type 'save'→ always insert.
       'update'→
         a) PK lookup
         b) natural-key lookup via lookup_fields
         c) insert if still no existing.
    """
    mapper     = inspect(model)
    valid_cols = {c.name for c in mapper.columns}
    pk_cols    = mapper.primary_key
    if len(pk_cols) != 1:
        raise RuntimeError(f"{model.__name__} composite PK not supported")
    pk_name    = pk_cols[0].name
    print("pk_name: ", pk_name)
    logger.info(f"\n\npk_name:: {pk_name}")

    # 0️⃣ Try to pull in a nested id if payload lacks a top-level one
    if pk_name not in data:
        nested = _find_nested_id(data)
        print("nested: ",nested)
        if nested:
            data[pk_name] = nested
    
    print("\n\ndata: ", data)
    # logger.info(f"\n\ndata:: {data[pk_name]}")

    # 1️⃣ Filter out any unexpected keys
    payload = {k: v for k, v in data.items() if k in valid_cols}

    existing = None
    if request_type == "update":
        # 2a) PK lookup
        if pk_name in payload:
            existing = db.get(model, payload[pk_name])
        # 2b) Natural-key lookup
        elif lookup_fields:
            filters = [getattr(model, fld) == payload[fld] for fld in lookup_fields]
            matches = db.query(model).filter(and_(*filters)).all()
            if len(matches) > 1:
                raise HTTPException(
                    400,
                    f"Ambiguous update for {model.__tablename__}: {len(matches)} rows match {lookup_fields}"
                )
            existing = matches[0] if matches else None

    # 3️⃣ Decide: insert vs update
    if request_type == "save" or (request_type == "update" and existing is None):
        payload.pop(pk_name, None)
        obj = model(**payload)
        db.add(obj)
        # flush so obj.id is populated
        db.flush()

        # now patch back into your original data dict
        new_id = getattr(obj, pk_name)
        _set_nested_id(data, new_id)

        return obj

    # 4️⃣ Patch existing row
    for key, val in payload.items():
        setattr(existing, key, val)
    return existing


def _create_or_update(db: Session, model, data: dict):
    # Use merge() for upsert on primary key
    obj = model(**data)
    return db.merge(obj)


def _save_or_update(
    db: Session,
    model,
    data: dict,
    employee_id,
    model_name: str,
):
    """
    Generic save-or-update helper.
    - If request_type == 'save': drops 'id', creates new instance.
    - If request_type == 'update': requires 'id', loads and updates.
    """
    rec_id = data.pop("id", None)
    if model_name == "employees":
        # employee update never creates new employee here
        rec_id = employee_id

    if rec_id and rec_id != employee_id:
        # update existing
        obj = db.query(model).get(rec_id)
        if not obj:
            raise ValueError(f"{model.__name__} id={rec_id} not found")
        for k, v in data.items():
            setattr(obj, k, v)
    else:
        # create new
        obj = model(employee_id=employee_id, **data) if model_name != "employees" else model(id=employee_id, **data)
        db.add(obj)

    db.commit()
    return obj

@register_handler("employees")
def handle_bio_data(db: Session, record):
    try:
        # _save_or_update(db, Employee, record.data, record.employee_id, "employees")
        payload = {**record.data, 'id': record.employee_id, 'organization_id': record.organization_id}
        _upsert_intelligent(db, Employee, payload, record.request_type)
    #     items = record.data if isinstance(record.data, list) else [record.data]
    #     print("handler request type:: ", record.request_type)
    #     for item in items:
    #         item["employee_id"] = record.employee_id
    #         obj = _upsert_intelligent(db, Employee, item, 
    #                                   record.request_type,
    #                                   lookup_fields=["first_name","last_name","email"])
    except Exception as e:
        logger.error("Error in handle_bio_data: %s", e)
        raise

@register_handler("academic_qualifications")
def handle_academic_qualifications(db: Session, record):
    try:
        # _save_or_update(
        #     db,
        #     AcademicQualification,
        #     record.data,
        #     record.employee_id,
        #     "academic_qualifications"
        # )
        items = record.data if isinstance(record.data, list) else [record.data]
        print("handler request type:: ", record.request_type)
        for item in items:
            item["employee_id"] = record.employee_id
            obj = _upsert_intelligent(db, AcademicQualification, item, 
                                      record.request_type,
                                      lookup_fields=["employee_id","degree"])
    except Exception as e:
        logger.error("Error in handle_academic_qualifications: %s", e)
        raise

@register_handler("professional_qualifications")
def handle_professional_qualifications(db: Session, record):
    try:
        items = record.data if isinstance(record.data, list) else [record.data]
        print("handler request type:: ", record.request_type)
        for item in items:
            item["employee_id"] = record.employee_id
            obj = _upsert_intelligent(db, ProfessionalQualification, item, 
                                      record.request_type,
                                      lookup_fields=["employee_id","qualification_name"])
    except Exception as e:
        logger.error("Error in handle_professional_qualifications: %s", e)
        raise
    # try:
    #     _save_or_update(
    #         db,
    #         ProfessionalQualification,
    #         record.data,
    #         record.employee_id,
    #         "professional_qualifications"
    #     )
    # except Exception as e:
    #     logger.error("Error in handle_professional_qualifications: %s", e)
    #     raise

@register_handler("employment_history")
def handle_employment_history(db: Session, record):
    try:
        # _save_or_update(
        #     db,
        #     EmploymentHistory,
        #     record.data,
        #     record.employee_id,
        #     "employment_history"
        # )
        items = record.data if isinstance(record.data, list) else [record.data]
        print("handler request type:: ", record.request_type)
        for item in items:
            item["employee_id"] = record.employee_id
            obj = _upsert_intelligent(db, EmploymentHistory, item, 
                                      record.request_type,
                                      lookup_fields=["employee_id","company"])
    except Exception as e:
        logger.error("Error in handle_employment_history: %s", e)
        raise

@register_handler("emergency_contacts")
def handle_emergency_contacts(db: Session, record):
    try:
      
        items = record.data if isinstance(record.data, list) else [record.data]
        print("handler request type:: ", record.request_type)
        for item in items:
            item["employee_id"] = record.employee_id
            obj = _upsert_intelligent(db, EmergencyContact, item, 
                                      record.request_type,
                                      lookup_fields=["employee_id","emergency_contact"])
    except Exception as e:
        logger.error("Error in handle_emergency_contacts: %s", e)
        raise

@register_handler("next_of_kin")
def handle_next_of_kin(db: Session, record):
    try:
        items = record.data if isinstance(record.data, list) else [record.data]
        print("handler request type:: ", record.request_type)
        for item in items:
            item["employee_id"] = record.employee_id
            obj = _upsert_intelligent(db, NextOfKin, item, 
                                      record.request_type,
                                      lookup_fields=["employee_id","nok_phone"])
    except Exception as e:
        logger.error("Error in handle_next_of_kin: %s", e)
        raise

@register_handler("employee_payment_details")
def handle_employee_payment_details(db: Session, record):
    try:
        items = record.data if isinstance(record.data, list) else [record.data]
        print("handler request type:: ", record.request_type)
        for item in items:
            item["employee_id"] = record.employee_id
            obj = _upsert_intelligent(db, EmployeePaymentDetail, item, 
                                      record.request_type,
                                      lookup_fields=["employee_id","payment_mode","is_verified"])

            # Ensure the boolean flag flips true if it was false
            if hasattr(obj, "is_verified") and not obj.is_verified:
                obj.is_verified = True

    except Exception as e:
        logger.error("Error in handle_employee_payment_details: %s", e)
        raise
   

@register_handler("promotion_requests")
def handle_promotion_requests(db: Session, record):
    try:
        _save_or_update(
            db,
            PromotionRequest,
            record.data,
            record.employee_id,
            "promotion_requests"
        )
    except Exception as e:
        logger.error("Error in handle_promotion_requests: %s", e)
        raise
































# # src/services/handlers/bio_data.py
# from Service.data_input_handlers import register_handler
# from Models.models import AcademicQualification
# from Models.models import ProfessionalQualification
# from Models.models import EmploymentHistory
# from Models.models import EmergencyContact
# from Models.models import NextOfKin
# from Models.models import PromotionRequest
# from datetime import datetime
# from sqlalchemy.orm import Session


# @register_handler("employees")
# def handle_bio_data(db, record):
#     from Models.models import Employee
#     emp = db.query(Employee).get(record.employee_id)
#     for k, v in record.data.items():
#         setattr(emp, k, v)
#     db.add(emp)
#     db.commit()





# # 1) AcademicQualification
# @register_handler("academic_qualifications")
# def handle_academic_qualifications(db: Session, record):
#     # record.data contains keys: degree, institution, year_obtained, details, (certificate_path merged at creation)
#     aq = AcademicQualification(
#         employee_id=record.employee_id,
#         **record.data
#     )
#     db.add(aq)
#     db.commit()

# # 2) ProfessionalQualification
# @register_handler("professional_qualifications")
# def handle_professional_qualifications(db: Session, record):
#     pq = ProfessionalQualification(
#         employee_id=record.employee_id,
#         **record.data
#     )
#     db.add(pq)
#     db.commit()

# # 3) EmploymentHistory
# @register_handler("employment_history")
# def handle_employment_history(db: Session, record):
#     eh = EmploymentHistory(
#         employee_id=record.employee_id,
#         # record.data should include job_title, company, start_date, etc.
#         **record.data
#     )
#     db.add(eh)
#     db.commit()

# # 4) EmergencyContact
# @register_handler("emergency_contacts")
# def handle_emergency_contacts(db: Session, record):
#     ec = EmergencyContact(
#         employee_id=record.employee_id,
#         **record.data
#     )
#     db.add(ec)
#     db.commit()

# # 5) NextOfKin
# @register_handler("next_of_kin")
# def handle_next_of_kin(db: Session, record):
#     nk = NextOfKin(
#         employee_id=record.employee_id,
#         **record.data
#     )
#     db.add(nk)
#     db.commit()

# # 6) PromotionRequest
# @register_handler("promotion_requests")
# def handle_promotion_requests(db: Session, record):
#     # record.data may include: current_rank_id, proposed_rank_id, promotion_effective_date, department_approved, etc.
#     pr = PromotionRequest(
#         employee_id=record.employee_id,
#         **record.data
#     )
#     # if department_approved or hr_approved flags already set in data, they'll be honored
#     # otherwise defaults apply.
#     db.add(pr)
#     db.commit()
