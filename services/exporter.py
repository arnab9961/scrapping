import io
import csv
import json
from typing import Generator
from services.database import get_db_connection

def _build_where_clause(search: str = "", industry: str = ""):
    conditions = []
    params = []
    if search.strip():
        term = f"%{search.strip()}%"
        conditions.append("(business_name LIKE ? OR contact_person LIKE ? OR phone LIKE ? OR email LIKE ? OR city LIKE ?)")
        params.extend([term, term, term, term, term])
    if industry.strip():
        conditions.append("industry LIKE ?")
        params.append(f"%{industry.strip()}%")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return where_clause, params

def stream_csv_export(search: str = "", industry: str = "") -> Generator[str, None, None]:
    """Streams full CSV export of leads matching filters."""
    output = io.StringIO()
    writer = csv.writer(output)

    headers = [
        "ID", "Business Name", "Contact Person", "Designation", "Industry",
        "Phone", "Phone Type", "Email", "Email Type", "Website", "Address", "City", "Country",
        "Completeness Score", "AI Confidence Score", "LinkedIn", "Facebook", "Twitter",
        "Validation Reason", "Scraping Mode", "Source URL", "Created At"
    ]
    writer.writerow(headers)
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    where_clause, params = _build_where_clause(search, industry)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM leads {where_clause} ORDER BY id DESC", tuple(params))
        for row in cursor:
            keys = row.keys()
            writer.writerow([
                row["id"],
                row["business_name"],
                row["contact_person"] or "N/A",
                row["designation"] or "N/A",
                row["industry"] or "N/A",
                row["phone"],
                row["phone_type"] if "phone_type" in keys else "UNKNOWN",
                row["email"] or "N/A",
                row["email_type"] if "email_type" in keys else "UNKNOWN",
                row["website"] or "N/A",
                row["address"] or "N/A",
                row["city"] or "N/A",
                row["country"] or "Bangladesh",
                row["completeness_score"] if "completeness_score" in keys else 0,
                row["ai_confidence_score"] or 0,
                row["linkedin_url"] if "linkedin_url" in keys else "",
                row["facebook_url"] if "facebook_url" in keys else "",
                row["twitter_url"] if "twitter_url" in keys else "",
                row["ai_validation_reason"] or "",
                row["scraping_mode"] or "http",
                row["source_url"] or "",
                row["created_at"]
            ])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

def stream_json_export(search: str = "", industry: str = "", json_lines: bool = False) -> Generator[str, None, None]:
    """Streams leads as formatted JSON array or JSON Lines (ndjson)."""
    where_clause, params = _build_where_clause(search, industry)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM leads {where_clause} ORDER BY id DESC", tuple(params))
        
        if json_lines:
            for row in cursor:
                d = dict(row)
                for json_col in ("secondary_phones", "secondary_emails"):
                    if json_col in d and isinstance(d[json_col], str):
                        try:
                            d[json_col] = json.loads(d[json_col])
                        except Exception:
                            pass
                yield json.dumps(d, ensure_ascii=False) + "\n"
        else:
            yield "[\n"
            first = True
            for row in cursor:
                d = dict(row)
                for json_col in ("secondary_phones", "secondary_emails"):
                    if json_col in d and isinstance(d[json_col], str):
                        try:
                            d[json_col] = json.loads(d[json_col])
                        except Exception:
                            pass
                prefix = "" if first else ",\n"
                first = False
                yield prefix + "  " + json.dumps(d, ensure_ascii=False)
            yield "\n]"

def generate_excel_export(search: str = "", industry: str = "") -> bytes:
    """Generates a formatted Excel (.xlsx) workbook using openpyxl."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Qualified Leads"

    headers = [
        "ID", "Business Name", "Contact Person", "Designation", "Industry",
        "Phone", "Phone Type", "Email", "Email Type", "Website", "City",
        "Completeness", "AI Score", "LinkedIn", "Facebook", "Source URL", "Created At"
    ]

    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    center_align = Alignment(horizontal="center", vertical="center")

    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align

    where_clause, params = _build_where_clause(search, industry)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM leads {where_clause} ORDER BY id DESC", tuple(params))
        for row in cursor:
            keys = row.keys()
            ws.append([
                row["id"],
                row["business_name"],
                row["contact_person"] or "N/A",
                row["designation"] or "N/A",
                row["industry"] or "N/A",
                row["phone"],
                row["phone_type"] if "phone_type" in keys else "UNKNOWN",
                row["email"] or "N/A",
                row["email_type"] if "email_type" in keys else "UNKNOWN",
                row["website"] or "N/A",
                row["city"] or "N/A",
                row["completeness_score"] if "completeness_score" in keys else 0,
                row["ai_confidence_score"] or 0,
                row["linkedin_url"] if "linkedin_url" in keys else "",
                row["facebook_url"] if "facebook_url" in keys else "",
                row["source_url"] or "",
                str(row["created_at"])
            ])

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 45)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
