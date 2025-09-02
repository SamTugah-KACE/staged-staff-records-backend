# app/routers/employee_download.py

from datetime import datetime
import io
import os
import json
import requests
from uuid import UUID
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

# ReportLab imports
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.utils import ImageReader

# PyPDF2 for merging PDFs
from PyPDF2 import PdfReader, PdfWriter

from Models.dynamic_models import EmployeeDynamicData
from database.db_session import get_db
from Crud.auth import get_current_user
from Models.models import (
    Employee,
    AcademicQualification,
    EmployeeDataInput,
    ProfessionalQualification,
    EmploymentHistory,
    EmergencyContact,
    NextOfKin,
    EmployeePaymentDetail,
    EmployeeType,
    Department,
    PromotionRequest,
    SalaryPayment,
    User,
)
from Models.Tenants.role import Role 
from Models.Tenants.organization import Organization, Branch, Rank
from functools import lru_cache


router = APIRouter()





def _download_image(path_or_url: str) -> Optional[ImageReader]:
    """
    Given a local filesystem path or an HTTP(S) URL, return an ImageReader.
    If neither works, return None.
    """
    try:
        if path_or_url.lower().startswith(("http://", "https://")):
            resp = requests.get(path_or_url, timeout=5)
            resp.raise_for_status()
            return ImageReader(io.BytesIO(resp.content))
        else:
            if os.path.exists(path_or_url):
                return ImageReader(path_or_url)
    except Exception:
        pass
    return None

@lru_cache(maxsize=128)
def _get_profile_image(path_or_url: str, target_size_mm: float = 30) -> Optional[ImageReader]:
    """
    Download (or load) the profile image and return an ImageReader
    scaled to target_size_mm (in mm). Caching avoids re-fetch on retries.
    """
    reader = _download_image(path_or_url)
    return reader  # drawImage will handle sizing


def _download_pdf_bytes(path_or_url: str) -> Optional[bytes]:
    """
    If path_or_url is a PDF (local or URL), return its bytes. Otherwise None.
    """
    try:
        if path_or_url.lower().endswith(".pdf"):
            if path_or_url.lower().startswith(("http://", "https://")):
                resp = requests.get(path_or_url, timeout=5)
                resp.raise_for_status()
                return resp.content
            else:
                if os.path.exists(path_or_url):
                    with open(path_or_url, "rb") as f:
                        return f.read()
    except Exception:
        pass
    return None


def _extract_url_from_field(raw: Any) -> Optional[str]:
    """
    Given a column that might be:
      - a plain URL string
      - a dict (JSONB) → {"file.pdf": "https://..."}
      - a JSON‐string (stored in a text column)
      Return the first URL found, or None.
    """
    if not raw:
        return None

    if isinstance(raw, dict):
        for k, v in raw.items():
            if k.lower() != "id" and isinstance(v, str):
                return v
        return None

    if isinstance(raw, str):
        # Try parsing as JSON
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                for k, v in parsed.items():
                    if k.lower() != "id" and isinstance(v, str):
                        return v
        except Exception:
            pass

        if raw.lower().startswith(("http://", "https://")):
            return raw

    return None


def _prepare_json_for_table_cell(raw: Any) -> Union[str, Paragraph]:
    """
    If a “Details” field is JSON/dict or a JSON‐string, convert it into
    a multiline Paragraph where each “KEY: Value” is on its own line (omitting any "id").
    Otherwise, return a plain string.
    """
    styles = getSampleStyleSheet()
    para_style = ParagraphStyle(
        "table_details", parent=styles["BodyText"], fontName="Helvetica", fontSize=10, leading=12, wordWrap="CJK"
    )

    parsed: Optional[Dict[str, Any]] = None
    if isinstance(raw, dict):
        parsed = raw
    else:
        try:
            parsed = json.loads(str(raw))
        except Exception:
            parsed = None

    if isinstance(parsed, dict):
        lines = []
        for k, v in parsed.items():
            if k.lower() == "id":
                continue
            key_cap = k.capitalize()
            lines.append(f"<b>{key_cap}:</b> {v}")
        if not lines:
            return ""
        # join with line breaks
        text = "<br/>".join(lines)
        return Paragraph(text, para_style)

    return str(raw)


def _calculate_column_widths(
    pdf: canvas.Canvas,
    headers: List[str],
    data_rows: List[List[Union[str, Paragraph]]],
    usable_width: float,
) -> List[float]:
    """
    Compute each column’s raw width (max of header/string widths),
    then either distribute evenly if total_raw < usable_width, or scale
    down if total_raw > usable_width. Always return column widths summing to usable_width.
    """
    pdf.setFont("Helvetica", 10)
    col_count = len(headers)

    # 1) Compute raw widths
    raw_widths = [0.0] * col_count
    for col_idx, header_text in enumerate(headers):
        w = pdf.stringWidth(header_text, "Helvetica", 10) + 6
        raw_widths[col_idx] = w

    for row in data_rows:
        for col_idx in range(col_count):
            cell = row[col_idx]
            if isinstance(cell, Paragraph):
                # measure the longest word in the paragraph
                text = cell.getPlainText()
                words = text.split()
                if words:
                    max_word = max(words, key=lambda w: pdf.stringWidth(w, "Helvetica", 10))
                else:
                    max_word = ""
                w = pdf.stringWidth(max_word, "Helvetica", 10) + 6
            else:
                w = pdf.stringWidth(str(cell), "Helvetica", 10) + 6

            if w > raw_widths[col_idx]:
                raw_widths[col_idx] = w

    total_raw = sum(raw_widths)

    # 2a) If total_raw < usable_width, distribute extra space evenly
    if total_raw < usable_width:
        extra = (usable_width - total_raw) / col_count
        return [max(2 * cm, raw_widths[i] + extra) for i in range(col_count)]

    # 2b) If total_raw > usable_width, scale down proportionally
    scale = usable_width / total_raw
    return [max(2 * cm, raw_widths[i] * scale) for i in range(col_count)]


def _apply_watermark(pdf: canvas.Canvas, text: str, page_width: float, page_height: float):
    pdf.saveState()
    pdf.translate(page_width/2, page_height/2)
    pdf.rotate(45)
    pdf.setFont("Helvetica-Bold", 50)
    try:
        pdf.setFillAlpha(0.1)
    except Exception:
        pass
    pdf.setFillColor(colors.grey)
    pdf.drawCentredString(0, 0, text)
    pdf.restoreState()

    
def _ensure_section_space(pdf: canvas.Canvas, current_y: float, needed_height: float) -> float:
    """
    If there isn't enough vertical space (current_y < needed_height + bottom_margin),
    start a new page and return a fresh y (page_height - top_margin).
    """
    bottom_margin = 3 * cm
    if current_y < bottom_margin + needed_height:
        pdf.showPage()
        new_y = A4[1] - 2 * cm  # leave 2cm top margin
        pdf.setFont("Helvetica", 11)
        return new_y
    return current_y

def _maybe_draw_watermark(pdf: canvas.Canvas, org: Organization, page_width: float, page_height: float):
    """
    If the org is government/public, draw 'Government of {Country}' diagonally.
    """
    typ = (org.type or "").lower()
    if typ in {"government", "public"} and getattr(org, "country", None):
        text = f"Government of {org.country}"
        pdf.saveState()
        pdf.setFont("Helvetica-Bold", 60)
        pdf.setFillColorRGB(0.7, 0.7, 0.7, alpha=0.1)
        # rotate about center
        pdf.translate(page_width/2, page_height/2)
        pdf.rotate(45)
        w = pdf.stringWidth(text, "Helvetica-Bold", 60)
        pdf.drawCentredString(0, 0, text)
        pdf.restoreState()

# def _show_page_with_watermark(pdf: canvas.Canvas, org: Organization):
#     pdf.showPage()
#     _maybe_draw_watermark(pdf, org, *A4)

# def _draw_letterhead(
#     pdf: canvas.Canvas,
#     org: Organization,
#     logo_paths: List[str],
#     page_width: float,
#     page_height: float
# ) -> float:
#     """
#     Draws a letterhead on the current page:
#      1) A top bar (thin line) across the full width
#      2) Left: Organization logo + name
#      3) Right: (Optional) second logo
#      4) Returns the y-coordinate below the letterhead where body begins.
#     """
#     # Dimensions
#     margin = 2 * cm
#     logo_mm = 20  # in mm
#     logo_size = logo_mm * (cm / 10)
#     line_y = page_height - margin + 5  # just above top margin

#     # 1) Thin top line
#     pdf.setStrokeColor(colors.grey)
#     pdf.setLineWidth(0.5)
#     pdf.line(margin, line_y, page_width - margin, line_y)

#     # 2) Load logos
#     imgs: List[ImageReader] = []
#     for lp in logo_paths:
#         if len(imgs) == 2: break
#         url = _extract_url_from_field(lp)
#         if url:
#             img = _download_image(url)
#             if img:
#                 imgs.append(img)

#     # 3) Draw first logo at margin, scaled
#     if imgs:
#         pdf.saveState()
#         pdf.setFillAlpha(0.1)  # very faint
#         try:
#             pdf.drawImage(imgs[0], margin, line_y - logo_size,
#                           width=logo_size, height=logo_size,
#                           preserveAspectRatio=True, mask="auto")
#         except Exception:
#             pass
#         pdf.restoreState()

#     # 4) Org name next to that logo
#     pdf.setFont("Helvetica-Bold", 18)
#     pdf.setFillColor(colors.black)
#     name_x = margin + (logo_size + 0.5*cm if imgs else 0)
#     name_y = line_y - (logo_size / 2) - 6
#     pdf.drawString(name_x, name_y, org.name)

#     # 5) Second logo at right, full opacity
#     if len(imgs) > 1:
#         r_x = page_width - margin - logo_size
#         try:
#             pdf.drawImage(imgs[1], r_x, line_y - logo_size,
#                           width=logo_size, height=logo_size,
#                           preserveAspectRatio=True, mask="auto")
#         except Exception:
#             pass

#     # 6) Return body-start Y (leave a bit of whitespace)
#     return line_y - logo_size - 1 * cm


# def _draw_page_watermark(
#     pdf: canvas.Canvas,
#     org: Organization,
#     page_width: float,
#     page_height: float
# ):
def _draw_page_watermark(
    pdf: canvas.Canvas,
    org: Organization,
    logo_paths: List[str],
    page_width: float,
    page_height: float
):
    """
    On each page, draw the faint left-logo watermark plus its text beneath.
    """
    # 1) Determine watermark text
    typ = (getattr(org, "type", "") or "").lower()
    wm_text = (
        f"Government of {getattr(org, 'country', '')}"
        if typ in {"government", "public"}
        else org.name or ""
    )

    # 2) Fetch first logo URL safely
    first_url = None
    if logo_paths:
        raw = logo_paths[0] or ""
        try:
            candidate = _extract_url_from_field(raw)
            if candidate:
                first_url = candidate
        except Exception:
            first_url = None

    # 3) Draw faint logo if available
    if first_url:
        img = _download_image(first_url)
        if img:
            pdf.saveState()
            # very light opacity
            try:
                pdf.setFillAlpha(0.05)
            except Exception:
                pass
            size = 40 * (cm / 10)  # 40 mm
            pdf.drawImage(
                img,
                x=2 * cm,
                y=2 * cm,
                width=size,
                height=size,
                preserveAspectRatio=True,
                mask="auto",
            )
            pdf.restoreState()

    # 4) Draw watermark text beneath logo
    pdf.saveState()
    try:
        pdf.setFillAlpha(0.08)
    except Exception:
        pass
    pdf.setFont("Helvetica-Bold", 24)
    pdf.setFillColor(colors.grey)
    # Reasonable left margin + just below the logo
    pdf.drawString(2 * cm, 2 * cm - 0.5 * cm, wm_text)
    pdf.restoreState()

# def _show_page_with_watermark(pdf: canvas.Canvas, watermark_text: str):
#     pdf.showPage()
#     _apply_watermark(pdf, watermark_text, *A4)

# def _show_page_with_watermark(pdf: canvas.Canvas, org: Organization):
#     """
#     Use instead of pdf.showPage() to get watermark on every page.
#     """
#     pdf.showPage()
#     _draw_letterhead(pdf, org, org.logos, *A4)      # re-draw letterhead
#     _draw_page_watermark(pdf, org, *A4)              # draw faint watermark

def _draw_letterhead(
    pdf: canvas.Canvas,
    org: Organization,
    logo_paths: List[str],
    employee: Employee,
    page_width: float,
    page_height: float
) -> float:
    """
    Letterhead:
     • top divider
     • left logo at `margin`
     • right logo at `page_width - margin - logo_size`
     • org.name wrapped & centered *between* logos, on the same vertical band
     • profile image under the right logo
    Returns the y where body content starts.
    """
    margin = 2 * cm
    logo_mm = 20
    logo_size = logo_mm * (cm / 10)
    line_y = page_height - margin + 5

    # 1) Divider line
    pdf.setStrokeColor(colors.grey)
    pdf.setLineWidth(0.5)
    pdf.line(margin, line_y, page_width - margin, line_y)

    # 2) Load logos
    imgs = []
    for lp in logo_paths[:2]:
        url = _extract_url_from_field(lp)
        img = _download_image(url) if url else None
        if img:
        
            imgs.append(img)

    # 3) Draw left logo
    left_x = margin
    if imgs:
        try:
            pdf.drawImage(imgs[0],
                          left_x, line_y - logo_size,
                          width=logo_size, height=logo_size,
                          preserveAspectRatio=True, mask="auto")
        except:
            pass
    left_edge = left_x + (logo_size if imgs else 0)

    # 4) Draw right logo
    right_x = page_width - margin - logo_size
    if len(imgs) > 1:
        try:
            pdf.drawImage(imgs[1],
                          right_x, line_y - logo_size,
                          width=logo_size, height=logo_size,
                          preserveAspectRatio=True, mask="auto")
        except:
            pass

    # 5) Org name paragraph, wrapped to gap [left_edge, right_x]
    gap_width = right_x - left_edge - 0.5 * cm
    styles = getSampleStyleSheet()
    name_style = ParagraphStyle(
        "OrgName",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=18,
        alignment=TA_CENTER,
    )
    para = Paragraph(org.name or "", name_style)
    wrapped_w, wrapped_h = para.wrap(gap_width, logo_size)
    # vertical center in the band from (line_y - logo_size) to line_y
    y_center = line_y - (logo_size / 2)
    y_para = y_center - (wrapped_h / 2)
    para.drawOn(pdf, left_edge + (gap_width - wrapped_w) / 2, y_para)

    # 6) Profile image beneath right logo
    prof = None
    if getattr(employee, "profile_image_path", None):
        prof = _get_profile_image(employee.profile_image_path)
    if prof:
        prof_y = line_y - logo_size - 0.5 * cm - logo_size
        try:
            pdf.drawImage(prof,
                          right_x, prof_y,
                          width=logo_size, height=logo_size,
                          preserveAspectRatio=True, mask="auto")
        except:
            pass
        bottom_y = prof_y
    else:
        bottom_y = min(y_para, line_y - logo_size)

    # 7) return start Y for page body (1cm below the lowest of name/profile)
    return bottom_y - 1 * cm


def _draw_page_watermark_and_footer(
    pdf: canvas.Canvas,
    org: Organization,
    logo_paths: List[str],
    page_width: float,
    page_height: float
):
    # --- Watermark (centered) ---
    # Determine text
    typ = (getattr(org, "type", "") or "").lower()
    wm_text = f"Government of {getattr(org,'country','')}" if typ in {"government","public"} else org.name or ""
    # Attempt to fetch first logo for watermark
    first_logo_url = _extract_url_from_field(logo_paths[0]) if logo_paths else None
    wm_img = _download_image(first_logo_url) if first_logo_url else None

    pdf.saveState()
    try: pdf.setFillAlpha(0.05)
    except: pass
    if wm_img:
        size = 100 * (cm/10)  # 100mm watermark
        pdf.drawImage(wm_img,
                      x=(page_width-size)/2, y=(page_height-size)/2,
                      width=size, height=size,
                      preserveAspectRatio=True, mask="auto")
    pdf.setFont("Helvetica-Bold", 12)
    pdf.setFillColor(colors.grey)
    pdf.drawCentredString(page_width/2, page_height/2 - 40, wm_text)
    pdf.restoreState()

    # --- Footer timestamp ---
    pdf.setFont("Helvetica", 8)
    pdf.setFillColor(colors.grey)
    ts = datetime.utcnow().strftime("%d %b %Y %H:%M UTC")
    pdf.drawCentredString(page_width/2, 1 * cm, ts)


def _show_page_with_watermark(
    pdf: canvas.Canvas,
    org: Organization,
    employee: Employee,
    logo_paths: List[str],
) -> float:
    pdf.showPage()
    body_y = _draw_letterhead(pdf, org, logo_paths, employee, *A4)
    _draw_page_watermark_and_footer(pdf, org, logo_paths, *A4)
    return body_y

def _draw_header(
    pdf: canvas.Canvas,
    org: Organization,
    employee: Employee,
    logo_paths: List[str],
    page_width: float,
    page_height: float,
) -> float:
    """
    Draw up to two logos, org name, and employee profile image.
    Return y below header for body content.
    """
    logo_size = 25 * (cm / 10)   # 25 mm
    profile_size = 30 * (cm / 10)  # 30 mm

    loaded_logos: List[ImageReader] = []
    for lp in logo_paths:
        if len(loaded_logos) >= 2:
            break
        url = _extract_url_from_field(lp)
        if url:
            img = _download_image(url)
            if img:
                loaded_logos.append(img)

    top_margin = page_height - 2 * cm

    if len(loaded_logos) >= 2:
        # Draw first logo at top-left
        try:
            pdf.drawImage(
                loaded_logos[0],
                x=2 * cm,
                y=top_margin - logo_size,
                width=logo_size,
                height=logo_size,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

        # Draw second logo at top-right
        right_logo_x = page_width - 2 * cm - logo_size
        try:
            pdf.drawImage(
                loaded_logos[1],
                x=right_logo_x,
                y=top_margin - logo_size,
                width=logo_size,
                height=logo_size,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

        # Draw organization name centered
        pdf.setFont("Helvetica-Bold", 16)
        org_name = org.name
        text_w = pdf.stringWidth(org_name, "Helvetica-Bold", 16)
        pdf.drawString((page_width - text_w) / 2, top_margin - (logo_size / 2) + 5, org_name)

        img_x = right_logo_x
        img_y = top_margin - logo_size - 3 * cm

    else:
        if loaded_logos:
            try:
                pdf.drawImage(
                    loaded_logos[0],
                    x=(page_width - logo_size) / 2,
                    y=top_margin - logo_size,
                    width=logo_size,
                    height=logo_size,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception:
                pass

            pdf.setFont("Helvetica-Bold", 16)
            org_name = org.name
            text_w = pdf.stringWidth(org_name, "Helvetica-Bold", 16)
            pdf.drawString((page_width - text_w) / 2, top_margin - logo_size - 1 * cm, org_name)

            img_x = page_width - 2 * cm - profile_size
            img_y = top_margin - logo_size - 3 * cm
        else:
            pdf.setFont("Helvetica-Bold", 16)
            org_name = org.name
            text_w = pdf.stringWidth(org_name, "Helvetica-Bold", 16)
            pdf.drawString((page_width - text_w) / 2, top_margin, org_name)

            img_x = page_width - 2 * cm - profile_size
            img_y = top_margin - 3 * cm

    if employee.profile_image_path:
        # prof_img = _download_image(employee.profile_image_path)
        prof_img = _get_profile_image(employee.profile_image_path)
        if prof_img:
            try:
                pdf.drawImage(
                    prof_img,
                    x=img_x,
                    y=img_y,
                    width=profile_size,
                    height=profile_size,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception:
                pass

    return img_y - 1 * cm


def _human_label(field_name: str) -> str:
    labels = {
        "first_name": "First Name",
        "middle_name": "Middle Name",
        "last_name": "Last Name",
        "gender": "Gender",
        "date_of_birth": "Date of Birth",
        "marital_status": "Marital Status",
        "email": "Email",
        "contact_info": "Contact Information",
        "hire_date": "Hire Date",
        "termination_date": "Termination Date",
        "custom_data": "Custom Data",
        "profile_image_path": "Profile Image",
        "staff_id": "Staff ID",
        "employee_type": "Employee Type",
        "rank": "Rank",
        "department": "Department",
        "branch": "Branch",
        # AcademicQualification
        "degree": "Degree",
        "institution": "Institution",
        "year_obtained": "Year Obtained",
        "details": "Details",
        # ProfessionalQualification
        "qualification_name": "Qualification Name",
        # EmploymentHistory
        "job_title": "Job Title",
        "company": "Company",
        "start_date": "Start Date",
        "end_date": "End Date",
        # EmergencyContact
        "name": "Name",
        "relation": "Relation",
        "emergency_phone": "Phone",
        "emergency_address": "Address",
        # NextOfKin
        "nok_phone": "Phone",
        "nok_address": "Address",
        # EmployeePaymentDetail
        "payment_mode": "Payment Mode",
        "bank_name": "Bank Name",
        "account_number": "Account Number",
        "mobile_money_provider": "Mobile Money Provider",
        "wallet_number": "Wallet Number",
        "additional_info": "Additional Info",
        "is_verified": "Verified",
        # EmployeeDataInput
        "data": "Data",
        "request_type": "Request Type",
        "request_date": "Request Date",
        "status": "Status",
        "data_type": "Data Type",
        "comments": "Comments",
        # PromotionRequest
        "current_rank": "Current Rank",
        "proposed_rank": "Proposed Rank",
        "promotion_effective_date": "Effective Date",
        "department_approved": "Dept Approved",
        "department_approval_date": "Dept Approval Date",
        "hr_approved": "HR Approved",
        "hr_approval_date": "HR Approval Date",
        "evidence_documents": "Evidence Documents",
        # SalaryPayment
        "amount": "Amount",
        "currency": "Currency",
        "payment_date": "Payment Date",
        "payment_method": "Payment Method",
        "transaction_id": "Transaction ID",
        "status": "Status",
        "approved_by": "Approved By",
        # EmployeeDynamicData
        "data_category": "Category",
        "created_at": "Created At",
        "updated_at": "Updated At",
    }
    return labels.get(field_name, field_name.replace("_", " ").title())


def _format_date(dt) -> str:
    if not dt:
        return ""
    if isinstance(dt, str):
        try:
            yyyy, mm, dd = dt.split("-")
            import calendar
            month_name = calendar.month_name[int(mm)]
            return f"{int(dd)}-{month_name}-{yyyy}"
        except Exception:
            return dt
    try:
        month_name = dt.strftime("%B")
        return dt.strftime(f"%d-{month_name}-%Y")
    except Exception:
        return str(dt)


def _draw_section_title(pdf: canvas.Canvas, title: str, y_pos: float, page_width: float) -> float:
    """
    Draw a section title. Assumes enough space has been checked beforehand.
    """
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(2 * cm, y_pos, f"• {title}")
    return y_pos - 1 * cm


def _draw_key_value_block(
    pdf: canvas.Canvas,
    data: dict,
    start_y: float,
    page_width: float,
) -> float:
    """
    Draw a series of “Key: Value” lines. If 'contact_info', indent each
    key/value on its own italicized line beneath the label. If there's
    not enough vertical space, move to a new page first.
    """
    pdf.setFont("Helvetica", 11)
    bottom_margin = 3 * cm

    # We will measure actual height of each “rendered item” (simple line or Paragraph)
    # to ensure no overlap—that solves the wide gap / overlapping issue.

    y = start_y
    for key, value in data.items():
        # Reserve enough room: label + at least one line of content
        needed_height = 1.2 * cm
        if y < bottom_margin + needed_height:
            pdf.showPage()
            y = A4[1] - 2 * cm
            pdf.setFont("Helvetica", 11)

        label = _human_label(key) + ":"
        if key in {
            "date_of_birth",
            "hire_date",
            "termination_date",
            "start_date",
            "end_date",
            "request_date",
            "promotion_effective_date",
            "department_approval_date",
            "hr_approval_date",
            "payment_date",
            "created_at",
            "updated_at",
        }:
            value = _format_date(value)

        if key == "contact_info":
            # 1) Draw the label
            pdf.drawString(2 * cm, y, label)
            y -= 0.8 * cm

            # 2) Parse contact_info (dict or JSON)
            parsed = {}
            if isinstance(value, dict):
                parsed = value
            else:
                try:
                    parsed = json.loads(str(value))
                except Exception:
                    parsed = {}

            # 3) For each k/v pair (ignore 'id'), italicize and measure exact height
            styles = getSampleStyleSheet()
            italic_style = ParagraphStyle(
                "italic_kv",
                parent=styles["BodyText"],
                fontName="Helvetica-Oblique",
                fontSize=10,
                leftIndent=1 * cm,
                leading=22,
                
            )

            for subk, subv in parsed.items():
                if subk.lower() == "id":
                    continue
                subk_cap = subk.capitalize()
                para_text = f"<b>{subk_cap}:</b> {subv}"
                para = Paragraph(para_text, italic_style)
                # wrap() returns (width, height) for the given available width
                max_width = page_width - 4 * cm
                w, h = para.wrap(max_width, A4[1])

                if y - h < bottom_margin:
                    pdf.showPage()
                    y = A4[1] - 2 * cm

                para.drawOn(pdf, 2 * cm + 0.5 * cm, y - h)
                y -= (h + 0.1 * cm)

        else:
            # Simple “Key: Value” line (string, or single‐line JSON fallback)
            if isinstance(value, (dict, str)):
                # Try JSON → single‐line “KEY: Value; KEY2: Value2”
                try:
                    if isinstance(value, str):
                        parsed = json.loads(value)
                    else:
                        parsed = value
                    if isinstance(parsed, dict):
                        parts = []
                        for sk, sv in parsed.items():
                            if sk.lower() == "id":
                                continue
                            parts.append(f"{sk.capitalize()}: {sv}")
                        text_line = "; ".join(parts)
                    else:
                        text_line = str(value)
                except Exception:
                    text_line = str(value)
            else:
                text_line = str(value)

            pdf.drawString(2 * cm, y, f"{label} {text_line}")
            y -= 0.8 * cm

        # If we’re too low, start a new page before the next key
        if y < bottom_margin + 0.8 * cm:
            pdf.showPage()
            y = A4[1] - 2 * cm
            pdf.setFont("Helvetica", 11)

    return y


def _draw_table(
    pdf: canvas.Canvas,
    headers: List[str],
    data_rows: List[List[Any]],
    start_y: float,
    page_width: float,
) -> float:
    """
    Draw a table that always stretches to 100% of usable width (page_width - 4*cm).
    Wrap any cell whose text exceeds its column width. Also guard against page breaks
    so that header + at least one data row appear together.
    """
    usable_width = page_width - 4 * cm
    bottom_margin = 3 * cm

    # Before drawing table, ensure we have space for title + header + one row
    approx_header_height = 14  # pts
    approx_row_height = 12     # pts
    needed_height = (approx_header_height + approx_row_height) * 1.2

    if start_y < bottom_margin + needed_height:
        pdf.showPage()
        start_y = A4[1] - 2 * cm
        pdf.setFont("Helvetica", 11)

    # Prepare “wrapped” data_rows: expand any “Details” cell containing JSON
    processed_rows: List[List[Union[str, Paragraph]]] = []
    for row in data_rows:
        new_row: List[Union[str, Paragraph]] = []
        for idx, cell in enumerate(row):
            header = headers[idx].lower()
            # If column is "details", try JSON→multiline Paragraph
            if header == "details":
                para = _prepare_json_for_table_cell(cell)
                new_row.append(para)
            else:
                text = str(cell)
                new_row.append(text)
        processed_rows.append(new_row)

    # Compute column widths summing exactly to usable_width
    col_widths = _calculate_column_widths(pdf, headers, processed_rows, usable_width)

    # Build final “prepared” table data, wrapping any cell that doesn't fit
    styles = getSampleStyleSheet()
    para_style = ParagraphStyle(
        "table_cell", parent=styles["BodyText"], fontName="Helvetica", fontSize=10, leading=12, wordWrap="CJK"
    )

    prepared: List[List[Union[str, Paragraph]]] = []
    for row_idx, row in enumerate([headers] + processed_rows):
        new_row: List[Union[str, Paragraph]] = []
        for col_idx, cell in enumerate(row):
            text = str(cell) if not isinstance(cell, Paragraph) else cell.getPlainText()
            # If already a Paragraph, keep
            if isinstance(cell, Paragraph):
                new_row.append(cell)
            else:
                if pdf.stringWidth(text, "Helvetica", 10) + 6 > col_widths[col_idx]:
                    new_row.append(Paragraph(text, para_style))
                else:
                    new_row.append(text)
        prepared.append(new_row)

    # Create and style the Table
    table = Table(prepared, colWidths=col_widths)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 11),
                ("FONTSIZE", (0, 1), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ]
        )
    )

    # Draw the table, handling page break if necessary
    w, h = table.wrapOn(pdf, usable_width, 0)
    if start_y - h < bottom_margin:
        pdf.showPage()
        start_y = A4[1] - 2 * cm
        w, h = table.wrapOn(pdf, usable_width, 0)

    table.drawOn(pdf, 2 * cm, start_y - h)
    return start_y - h - 1 * cm


@router.get(
    "/{employee_id}/download",
    response_class=StreamingResponse,
    summary="Download a full Employee PDF (all records, nicely formatted)",
)
def download_employee_pdf(
    employee_id: UUID,
    organization_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Fetch all records for a given employee (employee_id, organization_id),
    assemble them into a multi‐section PDF, then append any related PDF documents,
    and return the final merged PDF.
    """
    # ---------------------------------------
    # 1) Multi‐tenant security check
    # ---------------------------------------
    user_obj: User = current_user["user"]
    if user_obj.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not permitted for this organization."
        )

    # ---------------------------------------
    # 2) Fetch Organization
    # ---------------------------------------
    org: Organization = db.query(Organization).filter(
        Organization.id == organization_id,
        Organization.is_active == True
    ).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")

    # ---------------------------------------
    # 3) Fetch Employee
    # ---------------------------------------
    employee: Employee = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.organization_id == organization_id
    ).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found.")

    # ---------------------------------------
    # 4) Fetch Related Data
    # ---------------------------------------
    emp_type = None
    if employee.employee_type_id:
        emp_type = db.query(EmployeeType).filter(
            EmployeeType.id == employee.employee_type_id,
            EmployeeType.organization_id == organization_id
        ).first()

    rank_obj = None
    if employee.rank_id:
        rank_obj = db.query(Rank).filter(
            Rank.id == employee.rank_id,
            Rank.organization_id == organization_id
        ).first()

    dept_obj = None
    if employee.department_id:
        dept_obj = db.query(Department).filter(
            Department.id == employee.department_id,
            Department.organization_id == organization_id
        ).first()

    branch_obj = None
    if dept_obj and dept_obj.branch_id:
        branch_obj = db.query(Branch).filter(
            Branch.id == dept_obj.branch_id,
            Branch.organization_id == organization_id
        ).first()

    academic_qs: List[AcademicQualification] = db.query(AcademicQualification).filter(
        AcademicQualification.employee_id == employee_id
    ).all()

    prof_qs: List[ProfessionalQualification] = db.query(ProfessionalQualification).filter(
        ProfessionalQualification.employee_id == employee_id
    ).all()

    employment_hist: List[EmploymentHistory] = db.query(EmploymentHistory).filter(
        EmploymentHistory.employee_id == employee_id
    ).all()

    emergency_cts: List[EmergencyContact] = db.query(EmergencyContact).filter(
        EmergencyContact.employee_id == employee_id
    ).all()

    next_of_kin_qs: List[NextOfKin] = db.query(NextOfKin).filter(
        NextOfKin.employee_id == employee_id
    ).all()

    payment_details: List[EmployeePaymentDetail] = db.query(EmployeePaymentDetail).filter(
        EmployeePaymentDetail.employee_id == employee_id
    ).all()

    data_inputs: List[EmployeeDataInput] = db.query(EmployeeDataInput).filter(
        EmployeeDataInput.employee_id == employee_id
    ).all()

    promotion_reqs: List[PromotionRequest] = db.query(PromotionRequest).filter(
        PromotionRequest.employee_id == employee_id
    ).all()

    salary_payments: List[SalaryPayment] = db.query(SalaryPayment).filter(
        SalaryPayment.employee_id == employee_id
    ).all()

    dynamic_data_list: List[EmployeeDynamicData] = db.query(EmployeeDynamicData).filter(
        EmployeeDynamicData.employee_id == employee_id
    ).all()

    # ---------------------------------------
    # 5) Determine logo paths (up to two)
    # ---------------------------------------
    logo_paths: List[str] = []
    if org.logos:
        # org.logos might be a list, a dict, or a JSON string
        try:
            if isinstance(org.logos, list):
                logos_arr = org.logos
            elif isinstance(org.logos, dict):
                # Convert dict values to a list of URLs or "raw" entries
                logos_arr = list(org.logos.values())
            else:
                logos_arr = json.loads(org.logos)
                if isinstance(logos_arr, dict):
                    logos_arr = list(logos_arr.values())
        except Exception:
            # If JSON parsing fails, but it's a single raw string or dict, normalize:
            if isinstance(org.logos, dict):
                logos_arr = list(org.logos.values())
            else:
                logos_arr = []

        for lp in logos_arr:
            if len(logo_paths) >= 2:
                break
            if lp:
                logo_paths.append(lp)

     # Security & fetch org/employee omitted for brevity...
    # Determine watermark text:
    typ = (org.type or "").lower()
    watermark = f"Government of {org.country}" if typ in {"government","public"} else org.name

    # ---------------------------------------
    # 6) Build the “main” PDF with ReportLab
    # ---------------------------------------
    main_buffer = io.BytesIO()
    pdf = canvas.Canvas(main_buffer, pagesize=A4)
    page_width, page_height = A4

    # New: watermark first
    # _maybe_draw_watermark(pdf, org, page_width, page_height)
    # _apply_watermark(pdf, watermark, *A4)

    # Draw header (logos + org name + profile image)
    # y = _draw_header(pdf, org, employee, logo_paths, page_width, page_height)
    # Draw first page letterhead & watermark
    y = _draw_letterhead(pdf, org, logo_paths, employee, page_width, page_height)
    
    _draw_page_watermark_and_footer(pdf, org, logo_paths, page_width, page_height)
    

    # --- SECTION: Personal Information ---
    # Ensure there’s space for title + at least one line
    y = _ensure_section_space(pdf, y, needed_height=1.5 * cm)
    y = _draw_section_title(pdf, "Personal Information", y, page_width)

    full_name = employee.first_name
    if employee.middle_name:
        full_name += f" {employee.middle_name}"
    full_name += f" {employee.last_name}"

    personal_data = {
        "first_name": full_name,
        "gender": employee.gender,
        "date_of_birth": employee.date_of_birth,
        "marital_status": employee.marital_status,
        "email": employee.email,
        # contact_info may be JSON or JSON‐string
        "contact_info": employee.contact_info or {},
        "staff_id": employee.staff_id,
    }
    y = _draw_key_value_block(pdf, personal_data, y, page_width)

    # --- SECTION: Employment Details ---
    if any([emp_type, rank_obj, dept_obj, branch_obj, employee.hire_date, employee.termination_date]):
        y = _ensure_section_space(pdf, y, needed_height=1.5 * cm)
        y = _draw_section_title(pdf, "Employment Details", y, page_width)

        emp_detail_data: Dict[str, Any] = {}
        if emp_type:
            emp_detail_data["employee_type"] = emp_type.type_code
        if rank_obj:
            emp_detail_data["rank"] = rank_obj.name
        if dept_obj:
            emp_detail_data["department"] = dept_obj.name
        if branch_obj:
            emp_detail_data["branch"] = branch_obj.name
        emp_detail_data["hire_date"] = employee.hire_date
        emp_detail_data["termination_date"] = employee.termination_date

        y = _draw_key_value_block(pdf, emp_detail_data, y, page_width)

    # --- SECTION: Academic Qualifications ---
    academic_pdfs: List[bytes] = []
    if academic_qs:
        y = _ensure_section_space(pdf, y, needed_height=2 * cm)
        y = _draw_section_title(pdf, "Academic Qualifications", y, page_width)

        headers = ["Degree", "Institution", "Year Obtained", "Details"]
        data_rows: List[List[Any]] = []
        for a in academic_qs:
            url = _extract_url_from_field(a.certificate_path)
            if url:
                pdf_bytes = _download_pdf_bytes(url)
                if pdf_bytes:
                    academic_pdfs.append(pdf_bytes)
                else:
                    img_reader = _download_image(url)
                    if img_reader:
                        pdf.showPage()
                        pdf.setFont("Helvetica-Bold", 14)
                        pdf.drawString(2 * cm, page_height - 2 * cm, "Academic Certificate Image")
                        try:
                            pdf.drawImage(
                                img_reader,
                                x=2 * cm,
                                y=page_height - 6 * cm,
                                width=6 * cm,
                                height=6 * cm,
                                preserveAspectRatio=True,
                                mask="auto",
                            )
                        except Exception:
                            pdf.setFont("Helvetica", 10)
                            pdf.drawString(2 * cm, page_height - 3 * cm, url)

            # Prepare row; “Details” may be JSON
            data_rows.append([
                a.degree or "",
                a.institution or "",
                str(a.year_obtained) if a.year_obtained else "",
                a.details or "",
            ])

        y = _draw_table(pdf, headers, data_rows, y, page_width)
    else:
        academic_pdfs = []

    # --- SECTION: Professional Qualifications ---
    prof_pdfs: List[bytes] = []
    if prof_qs:
        y = _ensure_section_space(pdf, y, needed_height=2 * cm)
        y = _draw_section_title(pdf, "Professional Qualifications", y, page_width)

        headers = ["Qualification Name", "Institution", "Year Obtained", "Details"]
        data_rows: List[List[Any]] = []
        for p in prof_qs:
            url = _extract_url_from_field(p.license_path)
            if url:
                pdf_bytes = _download_pdf_bytes(url)
                if pdf_bytes:
                    prof_pdfs.append(pdf_bytes)
                else:
                    img_reader = _download_image(url)
                    if img_reader:
                        pdf.showPage()
                        pdf.setFont("Helvetica-Bold", 14)
                        pdf.drawString(2 * cm, page_height - 2 * cm, "Professional License Image")
                        try:
                            pdf.drawImage(
                                img_reader,
                                x=2 * cm,
                                y=page_height - 6 * cm,
                                width=6 * cm,
                                height=6 * cm,
                                preserveAspectRatio=True,
                                mask="auto",
                            )
                        except Exception:
                            pdf.setFont("Helvetica", 10)
                            pdf.drawString(2 * cm, page_height - 3 * cm, url)

            data_rows.append([
                p.qualification_name or "",
                p.institution or "",
                str(p.year_obtained) if p.year_obtained else "",
                p.details or "",
            ])
        y = _draw_table(pdf, headers, data_rows, y, page_width)
    else:
        prof_pdfs = []

    # --- SECTION: Employment History ---
    emp_pdfs: List[bytes] = []
    if employment_hist:
        y = _ensure_section_space(pdf, y, needed_height=2 * cm)
        y = _draw_section_title(pdf, "Employment History", y, page_width)

        headers = ["Job Title", "Company", "Start Date", "End Date", "Details"]
        data_rows: List[List[Any]] = []
        for e in employment_hist:
            url = _extract_url_from_field(e.documents_path)
            if url:
                pdf_bytes = _download_pdf_bytes(url)
                if pdf_bytes:
                    emp_pdfs.append(pdf_bytes)
                else:
                    img_reader = _download_image(url)
                    if img_reader:
                        pdf.showPage()
                        pdf.setFont("Helvetica-Bold", 14)
                        pdf.drawString(2 * cm, page_height - 2 * cm, "Employment Document Image")
                        try:
                            pdf.drawImage(
                                img_reader,
                                x=2 * cm,
                                y=page_height - 6 * cm,
                                width=6 * cm,
                                height=6 * cm,
                                preserveAspectRatio=True,
                                mask="auto",
                            )
                        except Exception:
                            pdf.setFont("Helvetica", 10)
                            pdf.drawString(2 * cm, page_height - 3 * cm, url)

            data_rows.append([
                e.job_title or "",
                e.company or "",
                _format_date(e.start_date),
                _format_date(e.end_date),
                e.details or "",
            ])
        y = _draw_table(pdf, headers, data_rows, y, page_width)
    else:
        emp_pdfs = []

    # --- SECTION: Emergency Contacts ---
    if emergency_cts:
        y = _ensure_section_space(pdf, y, needed_height=2 * cm)
        y = _draw_section_title(pdf, "Emergency Contacts", y, page_width)

        headers = ["Name", "Relation", "Phone", "Address", "Details"]
        data_rows: List[List[Any]] = []
        for ec in emergency_cts:
            data_rows.append([
                ec.name or "",
                ec.relation or "",
                ec.emergency_phone or "",
                ec.emergency_address or "",
                ec.details or "",
            ])
        y = _draw_table(pdf, headers, data_rows, y, page_width)

    # --- SECTION: Next of Kin ---
    if next_of_kin_qs:
        y = _ensure_section_space(pdf, y, needed_height=2 * cm)
        y = _draw_section_title(pdf, "Next of Kin", y, page_width)

        headers = ["Name", "Relation", "Phone", "Address", "Details"]
        data_rows: List[List[Any]] = []
        for nok in next_of_kin_qs:
            data_rows.append([
                nok.name or "",
                nok.relation or "",
                nok.nok_phone or "",
                nok.nok_address or "",
                nok.details or "",
            ])
        y = _draw_table(pdf, headers, data_rows, y, page_width)

    # --- SECTION: Payment Details ---
    if payment_details:
        y = _ensure_section_space(pdf, y, needed_height=2 * cm)
        y = _draw_section_title(pdf, "Payment Details", y, page_width)

        headers = [
            "Payment Mode", "Bank Name", "Account Number",
            "Mobile Money Provider", "Wallet Number", "Additional Info", "Verified"
        ]
        data_rows: List[List[Any]] = []
        for pd in payment_details:
            data_rows.append([
                pd.payment_mode or "",
                pd.bank_name or "",
                pd.account_number or "",
                pd.mobile_money_provider or "",
                pd.wallet_number or "",
                pd.additional_info or "",
                "Yes" if pd.is_verified else "No",
            ])
        y = _draw_table(pdf, headers, data_rows, y, page_width)

    # --- SECTION: Promotion Requests ---
    if promotion_reqs:
        y = _ensure_section_space(pdf, y, needed_height=2.5 * cm)
        y = _draw_section_title(pdf, "Promotion Requests", y, page_width)

        headers = [
            "Current Rank", "Proposed Rank", "Request Date",
            "Effective Date", "Dept Approved", "Dept Approval Date",
            "HR Approved", "HR Approval Date", "Comments"
        ]
        data_rows: List[List[Any]] = []
        for pr in promotion_reqs:
            curr_rank_name = ""
            prop_rank_name = ""
            if pr.current_rank_id:
                rr = db.query(Rank).filter(Rank.id == pr.current_rank_id).first()
                curr_rank_name = rr.name if rr else ""
            if pr.proposed_rank_id:
                rr2 = db.query(Rank).filter(Rank.id == pr.proposed_rank_id).first()
                prop_rank_name = rr2.name if rr2 else ""
            data_rows.append([
                curr_rank_name,
                prop_rank_name,
                _format_date(pr.request_date),
                _format_date(pr.promotion_effective_date),
                "Yes" if pr.department_approved else "No",
                _format_date(pr.department_approval_date),
                "Yes" if pr.hr_approved else "No",
                _format_date(pr.hr_approval_date),
                pr.comments or "",
            ])
        y = _draw_table(pdf, headers, data_rows, y, page_width)

    # --- SECTION: Salary Payments ---
    if salary_payments:
        y = _ensure_section_space(pdf, y, needed_height=2.5 * cm)
        y = _draw_section_title(pdf, "Salary Payments", y, page_width)

        headers = [
            "Amount", "Currency", "Payment Date", "Payment Method",
            "Transaction ID", "Status", "Approved By"
        ]
        data_rows: List[List[Any]] = []
        for sp in salary_payments:
            approver_name = ""
            if sp.approved_by:
                u = db.query(User).filter(User.id == sp.approved_by).first()
                approver_name = u.username if u else ""
            data_rows.append([
                str(sp.amount),
                sp.currency or "",
                _format_date(sp.payment_date),
                sp.payment_method or "",
                sp.transaction_id or "",
                sp.status or "",
                approver_name,
            ])
        y = _draw_table(pdf, headers, data_rows, y, page_width)

    # --- SECTION: Dynamic Employee Data ---
    if dynamic_data_list:
        y = _ensure_section_space(pdf, y, needed_height=2.5 * cm)
        y = _draw_section_title(pdf, "Dynamic Employee Data", y, page_width)

        headers = ["Category", "Data", "Created At", "Updated At"]
        data_rows: List[List[Any]] = []
        for dd in dynamic_data_list:
            data_rows.append([
                dd.data_category or "",
                dd.data or "",
                _format_date(dd.created_at),
                _format_date(dd.updated_at),
            ])
        y = _draw_table(pdf, headers, data_rows, y, page_width)

    # ---------------------------------------
    # 7) Gather all queued PDFs (academics/prof/employment)
    # ---------------------------------------
    pdfs_to_merge: List[bytes] = academic_pdfs + prof_pdfs + emp_pdfs

    # ---------------------------------------
    # 8) Explicitly end current page and save
    # ---------------------------------------
    # _show_page_with_watermark(pdf, watermark)
    # _show_page_with_watermark(pdf, org)
    _show_page_with_watermark(pdf, org, employee, logo_paths)
    # pdf.showPage()
    pdf.save()

    # Rewind the buffer so we can read it
    main_buffer.seek(0)
    main_pdf_reader = PdfReader(main_buffer)

    # ---------------------------------------
    # 9) Merge appended PDFs (if any)
    # ---------------------------------------
    if pdfs_to_merge:
        writer = PdfWriter()
        # Add pages from our generated PDF first
        for page in main_pdf_reader.pages:
            writer.add_page(page)

        # Then add pages from each appended PDF
        for pdf_b in pdfs_to_merge:
            try:
                r = PdfReader(io.BytesIO(pdf_b))
                for pg in r.pages:
                    writer.add_page(pg)
            except Exception:
                continue

        final_buffer = io.BytesIO()
        writer.write(final_buffer)
        final_buffer.seek(0)
        headers = {"Content-Disposition": f'attachment; filename="employee_{employee_id}.pdf"'}
        return StreamingResponse(final_buffer, media_type="application/pdf", headers=headers)
    else:
        main_buffer.seek(0)
        headers = {"Content-Disposition": f'attachment; filename="employee_{employee_id}.pdf"'}
        return StreamingResponse(main_buffer, media_type="application/pdf", headers=headers)















# # app/routers/employee_download.py

# import io
# import json
# import os
# from uuid import UUID
# from typing import Dict, List, Optional, Union

# from fastapi import APIRouter, Depends, HTTPException, status, Query
# from fastapi.responses import StreamingResponse
# from sqlalchemy.orm import Session
# from reportlab.lib.pagesizes import A4
# from reportlab.lib.units import cm
# from reportlab.pdfgen import canvas
# from reportlab.platypus import Table, TableStyle, Paragraph, Spacer, Image, SimpleDocTemplate, PageBreak
# from reportlab.lib import colors
# from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# from Models.dynamic_models import EmployeeDynamicData
# from database.db_session import get_db
# from Crud.auth import get_current_user
# from Models.models import (
#     Employee,
#     AcademicQualification,
#     EmployeeDataInput,
#     ProfessionalQualification,
#     EmploymentHistory,
#     EmergencyContact,
#     NextOfKin,
#     EmployeePaymentDetail,
#     EmployeeType,
#     Department,
#     PromotionRequest,
#     SalaryPayment,
#     User,
#     # ... import any other models you want to include
# )
# from Models.Tenants.role import Role 
# from Models.Tenants.organization import Organization, Branch, Rank
# import requests
# from reportlab.lib.utils import ImageReader
# from PyPDF2 import PdfReader, PdfWriter

# router = APIRouter()


# def _download_image(path_or_url: str) -> Optional[ImageReader]:
#     """
#     Given a local filesystem path or an HTTP(S) URL, return an ImageReader.
#     If neither works, return None.
#     """
#     try:
#         if path_or_url.lower().startswith(("http://", "https://")):
#             resp = requests.get(path_or_url, timeout=5)
#             resp.raise_for_status()
#             return ImageReader(io.BytesIO(resp.content))
#         else:
#             if os.path.exists(path_or_url):
#                 return ImageReader(path_or_url)
#     except Exception:
#         pass
#     return None


# def _download_pdf_bytes(path_or_url: str) -> Optional[bytes]:
#     """
#     If path_or_url is a PDF (local or URL), return its bytes. Otherwise None.
#     """
#     try:
#         if path_or_url.lower().endswith(".pdf"):
#             if path_or_url.lower().startswith(("http://", "https://")):
#                 resp = requests.get(path_or_url, timeout=5)
#                 resp.raise_for_status()
#                 return resp.content
#             else:
#                 if os.path.exists(path_or_url):
#                     with open(path_or_url, "rb") as f:
#                         return f.read()
#     except Exception:
#         pass
#     return None


# def _calculate_column_widths(
#     pdf: canvas.Canvas,
#     data: List[List[Union[str, Paragraph]]],
#     col_count: int,
#     max_total_width: float,
# ) -> List[float]:
#     """
#     Given a 2D list of data (strings or Paragraphs) and the available max_total_width,
#     compute each column’s width by measuring the widest piece of text in that column (for strings)
#     or using a heuristic for Paragraphs. Cap each column at max_total_width / col_count.
#     """
#     # Use default font for measurement
#     pdf.setFont("Helvetica", 10)
#     max_col_widths = [0.0] * col_count

#     for row in data:
#         for col_idx in range(col_count):
#             cell = row[col_idx]
#             if isinstance(cell, Paragraph):
#                 # For Paragraph, estimate width by splitting text and taking max word width
#                 text = cell.getPlainText()
#                 words = text.split()
#                 max_word = max(words, key=lambda w: pdf.stringWidth(w, "Helvetica", 10)) if words else ""
#                 width = pdf.stringWidth(max_word, "Helvetica", 10) + 4  # add small padding
#             else:
#                 width = pdf.stringWidth(str(cell), "Helvetica", 10) + 4
#             if width > max_col_widths[col_idx]:
#                 max_col_widths[col_idx] = width

#     # Cap each column at (max_total_width / col_count) but ensure at least some minimum
#     min_col_width = 2 * cm
#     cap = max_total_width / col_count
#     final_widths = []
#     for w in max_col_widths:
#         w_with_padding = w + 6  # further padding
#         final_widths.append(min(max(w_with_padding, min_col_width), cap))
#     return final_widths


# def _draw_header(
#     pdf: canvas.Canvas,
#     org: Organization,
#     employee: Employee,
#     logo_paths: List[str],
#     page_width: float,
#     page_height: float,
# ) -> float:
#     """
#     Draw org logos (up to two), org name, and employee’s profile image.
#     Return y-coordinate below header content.
#     """
#     logo_size = 25 * (cm / 10)
#     profile_size = 30 * (cm / 10)

#     loaded_logos: List[ImageReader] = []
#     for lp in logo_paths:
#         if len(loaded_logos) >= 2:
#             break
#         img = _download_image(lp)
#         if img:
#             loaded_logos.append(img)

#     top_margin = page_height - 2 * cm

#     if len(loaded_logos) >= 2:
#         # Left logo
#         try:
#             pdf.drawImage(
#                 loaded_logos[0],
#                 x=2 * cm,
#                 y=top_margin - logo_size,
#                 width=logo_size,
#                 height=logo_size,
#                 preserveAspectRatio=True,
#                 mask="auto",
#             )
#         except Exception:
#             pass
#         # Right logo
#         right_logo_x = page_width - 2 * cm - logo_size
#         try:
#             pdf.drawImage(
#                 loaded_logos[1],
#                 x=right_logo_x,
#                 y=top_margin - logo_size,
#                 width=logo_size,
#                 height=logo_size,
#                 preserveAspectRatio=True,
#                 mask="auto",
#             )
#         except Exception:
#             pass
#         pdf.setFont("Helvetica-Bold", 16)
#         org_name = org.name
#         text_w = pdf.stringWidth(org_name, "Helvetica-Bold", 16)
#         pdf.drawString((page_width - text_w) / 2, top_margin - (logo_size / 2) + 5, org_name)

#         img_x = right_logo_x
#         img_y = top_margin - logo_size - 3 * cm
#     else:
#         if loaded_logos:
#             try:
#                 pdf.drawImage(
#                     loaded_logos[0],
#                     x=(page_width - logo_size) / 2,
#                     y=top_margin - logo_size,
#                     width=logo_size,
#                     height=logo_size,
#                     preserveAspectRatio=True,
#                     mask="auto",
#                 )
#             except Exception:
#                 pass
#             pdf.setFont("Helvetica-Bold", 16)
#             org_name = org.name
#             text_w = pdf.stringWidth(org_name, "Helvetica-Bold", 16)
#             pdf.drawString((page_width - text_w) / 2, top_margin - logo_size - 1 * cm, org_name)

#             img_x = page_width - 2 * cm - profile_size
#             img_y = top_margin - logo_size - 3 * cm
#         else:
#             pdf.setFont("Helvetica-Bold", 16)
#             org_name = org.name
#             text_w = pdf.stringWidth(org_name, "Helvetica-Bold", 16)
#             pdf.drawString((page_width - text_w) / 2, top_margin, org_name)

#             img_x = page_width - 2 * cm - profile_size
#             img_y = top_margin - 3 * cm

#     if employee.profile_image_path:
#         prof_img = _download_image(employee.profile_image_path)
#         if prof_img:
#             try:
#                 pdf.drawImage(
#                     prof_img,
#                     x=img_x,
#                     y=img_y,
#                     width=profile_size,
#                     height=profile_size,
#                     preserveAspectRatio=True,
#                     mask="auto",
#                 )
#             except Exception:
#                 pass

#     return img_y - 1 * cm


# def _human_label(field_name: str) -> str:
#     labels = {
#         "first_name": "First Name",
#         "middle_name": "Middle Name",
#         "last_name": "Last Name",
#         "gender": "Gender",
#         "date_of_birth": "Date of Birth",
#         "marital_status": "Marital Status",
#         "email": "Email",
#         "contact_info": "Contact Information",
#         "hire_date": "Hire Date",
#         "termination_date": "Termination Date",
#         "custom_data": "Custom Data",
#         "profile_image_path": "Profile Image",
#         "staff_id": "Staff ID",
#         "employee_type": "Employee Type",
#         "rank": "Rank",
#         "department": "Department",
#         "branch": "Branch",
#         # AcademicQualification
#         "degree": "Degree",
#         "institution": "Institution",
#         "year_obtained": "Year Obtained",
#         "details": "Details",
#         "certificate_path": "Certificate",
#         # ProfessionalQualification
#         "qualification_name": "Qualification Name",
#         "license_path": "License",
#         # EmploymentHistory
#         "job_title": "Job Title",
#         "company": "Company",
#         "start_date": "Start Date",
#         "end_date": "End Date",
#         "documents_path": "Documents",
#         # EmergencyContact
#         "name": "Name",
#         "relation": "Relation",
#         "emergency_phone": "Phone",
#         "emergency_address": "Address",
#         # NextOfKin
#         "nok_phone": "Phone",
#         "nok_address": "Address",
#         # EmployeePaymentDetail
#         "payment_mode": "Payment Mode",
#         "bank_name": "Bank Name",
#         "account_number": "Account Number",
#         "mobile_money_provider": "Mobile Money Provider",
#         "wallet_number": "Wallet Number",
#         "additional_info": "Additional Info",
#         "is_verified": "Verified",
#         # EmployeeDataInput
#         "data": "Data",
#         "request_type": "Request Type",
#         "request_date": "Request Date",
#         "status": "Status",
#         "data_type": "Data Type",
#         "comments": "Comments",
#         # PromotionRequest
#         "current_rank": "Current Rank",
#         "proposed_rank": "Proposed Rank",
#         "promotion_effective_date": "Effective Date",
#         "department_approved": "Dept Approved",
#         "department_approval_date": "Dept Approval Date",
#         "hr_approved": "HR Approved",
#         "hr_approval_date": "HR Approval Date",
#         "evidence_documents": "Evidence Documents",
#         # SalaryPayment
#         "amount": "Amount",
#         "currency": "Currency",
#         "payment_date": "Payment Date",
#         "payment_method": "Payment Method",
#         "transaction_id": "Transaction ID",
#         "status": "Status",
#         "approved_by": "Approved By",
#         # EmployeeDynamicData
#         "data_category": "Category",
#         "created_at": "Created At",
#         "updated_at": "Updated At",
#     }
#     return labels.get(field_name, field_name.replace("_", " ").title())


# def _format_date(dt) -> str:
#     if not dt:
#         return ""
#     if isinstance(dt, str):
#         try:
#             yyyy, mm, dd = dt.split("-")
#             import calendar
#             month_name = calendar.month_name[int(mm)]
#             return f"{int(dd)}-{month_name}-{yyyy}"
#         except Exception:
#             return dt
#     try:
#         month_name = dt.strftime("%B")
#         return dt.strftime(f"%d-{month_name}-%Y")
#     except Exception:
#         return str(dt)


# def _draw_section_title(pdf: canvas.Canvas, title: str, y_pos: float, page_width: float) -> float:
#     pdf.setFont("Helvetica-Bold", 14)
#     pdf.drawString(2 * cm, y_pos, f"• {title}")
#     return y_pos - 1 * cm


# def _draw_key_value_block(pdf: canvas.Canvas, data: dict, start_y: float, page_width: float) -> float:
#     pdf.setFont("Helvetica", 11)
#     y = start_y
#     line_height = 0.8 * cm

#     for key, value in data.items():
#         label = _human_label(key) + ":"
#         if key in {
#             "date_of_birth",
#             "hire_date",
#             "termination_date",
#             "start_date",
#             "end_date",
#             "request_date",
#             "promotion_effective_date",
#             "department_approval_date",
#             "hr_approval_date",
#             "payment_date",
#             "created_at",
#             "updated_at",
#         }:
#             value = _format_date(value)
#         if isinstance(value, dict):
#             try:
#                 value = json.dumps(value)
#             except Exception:
#                 value = str(value)
#         text = f"{label} {value if value is not None else ''}"
#         pdf.drawString(2 * cm, y, text)
#         y -= line_height
#         if y < 3 * cm:
#             pdf.showPage()
#             y = A4[1] - 3 * cm
#             pdf.setFont("Helvetica", 11)
#     return y


# def _draw_table(
#     pdf: canvas.Canvas,
#     data_rows: List[List[str]],
#     headers: List[str],
#     start_y: float,
#     page_width: float,
# ) -> float:
#     """
#     Draw a table with dynamic column widths and wrapped text. Returns new y.
#     data_rows: list of rows, each a list of strings.
#     headers: list of header strings.
#     """
#     # Prepare combined data to measure widths
#     combined = [headers] + data_rows
#     col_count = len(headers)
#     usable_width = page_width - 4 * cm

#     # Convert text to Paragraphs if they exceed a certain length
#     # Also measure raw string widths for dynamic sizing
#     styles = getSampleStyleSheet()
#     para_style = ParagraphStyle(
#         "table_cell", parent=styles["BodyText"], fontName="Helvetica", fontSize=10, leading=12, wordWrap="CJK"
#     )

#     # Build a 2D list of either strings or Paragraphs
#     prepared_data: List[List[Union[str, Paragraph]]] = []
#     for r_idx, row in enumerate(combined):
#         new_row = []
#         for c_idx, cell in enumerate(row):
#             text = str(cell)
#             # If text width is greater than a fraction of usable width, wrap as Paragraph
#             if pdf.stringWidth(text, "Helvetica", 10) > usable_width / col_count:
#                 new_row.append(Paragraph(text, para_style))
#             else:
#                 new_row.append(text)
#         prepared_data.append(new_row)

#     # Calculate dynamic col widths
#     col_widths = _calculate_column_widths(pdf, prepared_data, col_count, usable_width)

#     table = Table(prepared_data, colWidths=col_widths)
#     table.setStyle(
#         TableStyle(
#             [
#                 ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
#                 ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
#                 ("ALIGN", (0, 0), (-1, -1), "LEFT"),
#                 ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
#                 ("FONTSIZE", (0, 0), (-1, 0), 11),
#                 ("FONTSIZE", (0, 1), (-1, -1), 10),
#                 ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
#                 ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
#             ]
#         )
#     )

#     w, h = table.wrapOn(pdf, usable_width, 0)
#     if start_y - h < 2 * cm:
#         pdf.showPage()
#         start_y = A4[1] - 3 * cm

#     table.drawOn(pdf, 2 * cm, start_y - h)
#     return start_y - h - 1 * cm


# @router.get(
#     "/{employee_id}/download",
#     response_class=StreamingResponse,
#     summary="Download a full Employee PDF (all records, nicely formatted)",
# )
# def download_employee_pdf(
#     employee_id: UUID,
#     organization_id: UUID = Query(...),
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user),
# ):
#     """
#     Fetch all records for a given employee (employee_id, organization_id),
#     assemble them into a multi-section PDF, then append any related PDF documents,
#     and return the final merged PDF.
#     """
#     # 1) Security: ensure the requester’s org matches
#     user_obj: User  = current_user["user"]
#     if user_obj.organization_id != organization_id:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Not permitted for this organization."
#         )

#     # 2) Fetch Organization
#     org: Organization = db.query(Organization).filter(
#         Organization.id == organization_id,
#         Organization.is_active == True
#     ).first()
#     if not org:
#         raise HTTPException(status_code=404, detail="Organization not found.")

#     # 3) Fetch Employee
#     employee: Employee = db.query(Employee).filter(
#         Employee.id == employee_id,
#         Employee.organization_id == organization_id
#     ).first()
#     if not employee:
#         raise HTTPException(status_code=404, detail="Employee not found.")

#     # 4) Fetch all related data sets (synchronously) before generating PDF
#     emp_type = None
#     if employee.employee_type_id:
#         emp_type = db.query(EmployeeType).filter(
#             EmployeeType.id == employee.employee_type_id,
#             EmployeeType.organization_id == organization_id
#         ).first()

#     rank_obj = None
#     if employee.rank_id:
#         rank_obj = db.query(Rank).filter(
#             Rank.id == employee.rank_id,
#             Rank.organization_id == organization_id
#         ).first()

#     dept_obj = None
#     if employee.department_id:
#         dept_obj = db.query(Department).filter(
#             Department.id == employee.department_id,
#             Department.organization_id == organization_id
#         ).first()

#     branch_obj = None
#     if dept_obj and dept_obj.branch_id:
#         branch_obj = db.query(Branch).filter(
#             Branch.id == dept_obj.branch_id,
#             Branch.organization_id == organization_id
#         ).first()

#     academic_qs: List[AcademicQualification] = db.query(AcademicQualification).filter(
#         AcademicQualification.employee_id == employee_id
#     ).all()

#     prof_qs: List[ProfessionalQualification] = db.query(ProfessionalQualification).filter(
#         ProfessionalQualification.employee_id == employee_id
#     ).all()

#     employment_hist: List[EmploymentHistory] = db.query(EmploymentHistory).filter(
#         EmploymentHistory.employee_id == employee_id
#     ).all()

#     emergency_cts: List[EmergencyContact] = db.query(EmergencyContact).filter(
#         EmergencyContact.employee_id == employee_id
#     ).all()

#     next_of_kin_qs: List[NextOfKin] = db.query(NextOfKin).filter(
#         NextOfKin.employee_id == employee_id
#     ).all()

#     payment_details: List[EmployeePaymentDetail] = db.query(EmployeePaymentDetail).filter(
#         EmployeePaymentDetail.employee_id == employee_id
#     ).all()

#     data_inputs: List[EmployeeDataInput] = db.query(EmployeeDataInput).filter(
#         EmployeeDataInput.employee_id == employee_id
#     ).all()

#     promotion_reqs: List[PromotionRequest] = db.query(PromotionRequest).filter(
#         PromotionRequest.employee_id == employee_id
#     ).all()

#     salary_payments: List[SalaryPayment] = db.query(SalaryPayment).filter(
#         SalaryPayment.employee_id == employee_id
#     ).all()

#     dynamic_data_list: List[EmployeeDynamicData] = db.query(EmployeeDynamicData).filter(
#         EmployeeDynamicData.employee_id == employee_id
#     ).all()

#     # 5) Determine up to two logo paths
#     logo_paths: List[str] = []
#     if org.logos:
#         try:
#             logos_arr = org.logos if isinstance(org.logos, list) else json.loads(org.logos)
#         except Exception:
#             logos_arr = org.logos if isinstance(org.logos, list) else []
#         for lp in logos_arr:
#             if len(logo_paths) >= 2:
#                 break
#             if lp:
#                 logo_paths.append(lp)

#     # 6) Build initial PDF (without appending external PDFs yet)
#     main_buffer = io.BytesIO()
#     pdf = canvas.Canvas(main_buffer, pagesize=A4)
#     page_width, page_height = A4

#     y = _draw_header(pdf, org, employee, logo_paths, page_width, page_height)

#     # SECTION: Personal Information
#     y = _draw_section_title(pdf, "Personal Information", y, page_width)
#     full_name = employee.first_name
#     if employee.middle_name:
#         full_name += f" {employee.middle_name}"
#     full_name += f" {employee.last_name}"
#     personal_data = {
#         "first_name": full_name,
#         "gender": employee.gender,
#         "date_of_birth": employee.date_of_birth,
#         "marital_status": employee.marital_status,
#         "email": employee.email,
#         "contact_info": employee.contact_info or {},
#         "staff_id": employee.staff_id,
#     }
#     y = _draw_key_value_block(pdf, personal_data, y, page_width)

#     # SECTION: Employment Details
#     if any([emp_type, rank_obj, dept_obj, branch_obj, employee.hire_date, employee.termination_date]):
#         y = _draw_section_title(pdf, "Employment Details", y, page_width)
#         emp_detail_data: Dict[str, Optional[str]] = {}
#         if emp_type:
#             emp_detail_data["employee_type"] = f"{emp_type.type_code} - {emp_type.description or ''}"
#         if rank_obj:
#             emp_detail_data["rank"] = rank_obj.name
#         if dept_obj:
#             emp_detail_data["department"] = dept_obj.name
#         if branch_obj:
#             emp_detail_data["branch"] = branch_obj.name
#         emp_detail_data["hire_date"] = employee.hire_date
#         emp_detail_data["termination_date"] = employee.termination_date

#         y = _draw_key_value_block(pdf, emp_detail_data, y, page_width)

#     # SECTION: Academic Qualifications
#     if academic_qs:
#         y = _draw_section_title(pdf, "Academic Qualifications", y, page_width)
#         headers = ["Degree", "Institution", "Year Obtained", "Details", "Certificate"]
#         data_rows = []
#         for a in academic_qs:
#             data_rows.append([
#                 a.degree or "",
#                 a.institution or "",
#                 str(a.year_obtained) if a.year_obtained else "",
#                 str(a.details) if a.details else "",
#                 a.certificate_path or "",
#             ])
#         y = _draw_table(pdf, data_rows, headers, y, page_width)

#     # SECTION: Professional Qualifications
#     if prof_qs:
#         y = _draw_section_title(pdf, "Professional Qualifications", y, page_width)
#         headers = ["Qualification Name", "Institution", "Year Obtained", "Details", "License"]
#         data_rows = []
#         for p in prof_qs:
#             data_rows.append([
#                 p.qualification_name or "",
#                 p.institution or "",
#                 str(p.year_obtained) if p.year_obtained else "",
#                 str(p.details) if p.details else "",
#                 p.license_path or "",
#             ])
#         y = _draw_table(pdf, data_rows, headers, y, page_width)

#     # SECTION: Employment History
#     if employment_hist:
#         y = _draw_section_title(pdf, "Employment History", y, page_width)
#         headers = ["Job Title", "Company", "Start Date", "End Date", "Details", "Documents"]
#         data_rows = []
#         for e in employment_hist:
#             data_rows.append([
#                 e.job_title or "",
#                 e.company or "",
#                 _format_date(e.start_date),
#                 _format_date(e.end_date),
#                 str(e.details) if e.details else "",
#                 e.documents_path or "",
#             ])
#         y = _draw_table(pdf, data_rows, headers, y, page_width)

#     # SECTION: Emergency Contacts
#     if emergency_cts:
#         y = _draw_section_title(pdf, "Emergency Contacts", y, page_width)
#         headers = ["Name", "Relation", "Phone", "Address", "Details"]
#         data_rows = []
#         for ec in emergency_cts:
#             data_rows.append([
#                 ec.name or "",
#                 ec.relation or "",
#                 ec.emergency_phone or "",
#                 ec.emergency_address or "",
#                 str(ec.details) if ec.details else "",
#             ])
#         y = _draw_table(pdf, data_rows, headers, y, page_width)

#     # SECTION: Next of Kin
#     if next_of_kin_qs:
#         y = _draw_section_title(pdf, "Next of Kin", y, page_width)
#         headers = ["Name", "Relation", "Phone", "Address", "Details"]
#         data_rows = []
#         for nok in next_of_kin_qs:
#             data_rows.append([
#                 nok.name or "",
#                 nok.relation or "",
#                 nok.nok_phone or "",
#                 nok.nok_address or "",
#                 str(nok.details) if nok.details else "",
#             ])
#         y = _draw_table(pdf, data_rows, headers, y, page_width)

#     # SECTION: Payment Details
#     if payment_details:
#         y = _draw_section_title(pdf, "Payment Details", y, page_width)
#         headers = [
#             "Payment Mode", "Bank Name", "Account Number",
#             "Mobile Money Provider", "Wallet Number", "Additional Info", "Verified"
#         ]
#         data_rows = []
#         for pd in payment_details:
#             data_rows.append([
#                 pd.payment_mode or "",
#                 pd.bank_name or "",
#                 pd.account_number or "",
#                 pd.mobile_money_provider or "",
#                 pd.wallet_number or "",
#                 str(pd.additional_info) if pd.additional_info else "",
#                 "Yes" if pd.is_verified else "No",
#             ])
#         y = _draw_table(pdf, data_rows, headers, y, page_width)

#     # SECTION: Employee Data Inputs
#     if data_inputs:
#         y = _draw_section_title(pdf, "Employee Data Inputs", y, page_width)
#         headers = ["Data Type", "Request Type", "Request Date", "Status", "Comments", "Data"]
#         data_rows = []
#         for di in data_inputs:
#             data_rows.append([
#                 di.data_type or "",
#                 di.request_type or "",
#                 _format_date(di.request_date),
#                 di.status or "",
#                 di.comments or "",
#                 json.dumps(di.data) if di.data else "",
#             ])
#         y = _draw_table(pdf, data_rows, headers, y, page_width)

#     # SECTION: Promotion Requests
#     if promotion_reqs:
#         y = _draw_section_title(pdf, "Promotion Requests", y, page_width)
#         headers = [
#             "Current Rank", "Proposed Rank", "Request Date",
#             "Effective Date", "Dept Approved", "Dept Approval Date",
#             "HR Approved", "HR Approval Date", "Evidence Docs", "Comments"
#         ]
#         data_rows = []
#         for pr in promotion_reqs:
#             curr_rank_name = ""
#             prop_rank_name = ""
#             if pr.current_rank_id:
#                 rr = db.query(Rank).filter(Rank.id == pr.current_rank_id).first()
#                 curr_rank_name = rr.name if rr else ""
#             if pr.proposed_rank_id:
#                 rr2 = db.query(Rank).filter(Rank.id == pr.proposed_rank_id).first()
#                 prop_rank_name = rr2.name if rr2 else ""
#             data_rows.append([
#                 curr_rank_name,
#                 prop_rank_name,
#                 _format_date(pr.request_date),
#                 _format_date(pr.promotion_effective_date),
#                 "Yes" if pr.department_approved else "No",
#                 _format_date(pr.department_approval_date),
#                 "Yes" if pr.hr_approved else "No",
#                 _format_date(pr.hr_approval_date),
#                 ", ".join(pr.evidence_documents) if pr.evidence_documents else "",
#                 pr.comments or "",
#             ])
#         y = _draw_table(pdf, data_rows, headers, y, page_width)

#     # SECTION: Salary Payments
#     if salary_payments:
#         y = _draw_section_title(pdf, "Salary Payments", y, page_width)
#         headers = [
#             "Amount", "Currency", "Payment Date", "Payment Method",
#             "Transaction ID", "Status", "Approved By"
#         ]
#         data_rows = []
#         for sp in salary_payments:
#             approver_name = ""
#             if sp.approved_by:
#                 u = db.query(User).filter(User.id == sp.approved_by).first()
#                 approver_name = u.username if u else ""
#             data_rows.append([
#                 str(sp.amount),
#                 sp.currency or "",
#                 _format_date(sp.payment_date),
#                 sp.payment_method or "",
#                 sp.transaction_id or "",
#                 sp.status or "",
#                 approver_name,
#             ])
#         y = _draw_table(pdf, data_rows, headers, y, page_width)

#     # SECTION: Dynamic Employee Data
#     if dynamic_data_list:
#         y = _draw_section_title(pdf, "Dynamic Employee Data", y, page_width)
#         headers = ["Category", "Data", "Created At", "Updated At"]
#         data_rows = []
#         for dd in dynamic_data_list:
#             data_rows.append([
#                 dd.data_category or "",
#                 json.dumps(dd.data) if dd.data else "",
#                 _format_date(dd.created_at),
#                 _format_date(dd.updated_at),
#             ])
#         y = _draw_table(pdf, data_rows, headers, y, page_width)

#     # 7) “Other Files” handling: separate PDF files vs. image files
#     pdfs_to_merge: List[bytes] = []
#     for a in academic_qs:
#         if a.certificate_path:
#             pdf_bytes = _download_pdf_bytes(a.certificate_path)
#             if pdf_bytes:
#                 pdfs_to_merge.append(pdf_bytes)
#             else:
#                 # Draw certificate path as image or link
#                 pdf.showPage()
#                 pdf.setFont("Helvetica-Bold", 14)
#                 pdf.drawString(2 * cm, page_height - 2 * cm, "Academic Certificate")
#                 pdf.setFont("Helvetica", 11)
#                 pdf.drawString(2 * cm, page_height - 3 * cm, a.certificate_path)

#     for p in prof_qs:
#         if p.license_path:
#             pdf_bytes = _download_pdf_bytes(p.license_path)
#             if pdf_bytes:
#                 pdfs_to_merge.append(pdf_bytes)
#             else:
#                 pdf.showPage()
#                 pdf.setFont("Helvetica-Bold", 14)
#                 pdf.drawString(2 * cm, page_height - 2 * cm, "Professional License")
#                 pdf.setFont("Helvetica", 11)
#                 pdf.drawString(2 * cm, page_height - 3 * cm, p.license_path)

#     for e in employment_hist:
#         if e.documents_path:
#             pdf_bytes = _download_pdf_bytes(e.documents_path)
#             if pdf_bytes:
#                 pdfs_to_merge.append(pdf_bytes)
#             else:
#                 pdf.showPage()
#                 pdf.setFont("Helvetica-Bold", 14)
#                 pdf.drawString(2 * cm, page_height - 2 * cm, "Employment Documents")
#                 pdf.setFont("Helvetica", 11)
#                 pdf.drawString(2 * cm, page_height - 3 * cm, e.documents_path)

#     # 8) Finalize the initial PDF
#     pdf.save()
#     main_buffer.seek(0)
#     main_pdf_reader = PdfReader(main_buffer)

#     # 9) Merge appended PDFs (if any)
#     if pdfs_to_merge:
#         writer = PdfWriter()
#         # Add pages from our generated PDF first
#         for page in main_pdf_reader.pages:
#             writer.add_page(page)
#         # Then add pages from each appended PDF
#         for pdf_b in pdfs_to_merge:
#             try:
#                 r = PdfReader(io.BytesIO(pdf_b))
#                 for page in r.pages:
#                     writer.add_page(page)
#             except Exception:
#                 # If merging fails, skip that PDF
#                 continue
#         final_buffer = io.BytesIO()
#         writer.write(final_buffer)
#         final_buffer.seek(0)
#         headers = {"Content-Disposition": f'attachment; filename="employee_{employee_id}.pdf"'}
#         return StreamingResponse(final_buffer, media_type="application/pdf", headers=headers)
#     else:
#         # No PDFs to merge: return main_buffer directly
#         headers = {"Content-Disposition": f'attachment; filename="employee_{employee_id}.pdf"'}
#         return StreamingResponse(main_buffer, media_type="application/pdf", headers=headers)
