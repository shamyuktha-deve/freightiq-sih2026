import csv
import io
from datetime import datetime, date
from typing import List, Tuple
from sqlalchemy.orm import Session
from app.models.models import FreightRate, Route
from app.schemas.schemas import CSVRowValidationError, CSVUploadResponse

REQUIRED_COLUMNS = ["route_id", "rate_date", "spot_rate", "currency", "unit", "data_source"]

def parse_and_validate_csv(
    file_content: bytes,
    filename: str,
    db: Session
) -> CSVUploadResponse:
    """
    Parses and validates multipart CSV freight upload.
    Ensures strict validation: no silent insertions, reports exact row numbers and field errors.
    """
    try:
        text_stream = io.StringIO(file_content.decode("utf-8-sig"))
    except UnicodeDecodeError:
        try:
            text_stream = io.StringIO(file_content.decode("latin-1"))
        except Exception as e:
            return CSVUploadResponse(
                filename=filename,
                rows_received=0,
                rows_inserted=0,
                rows_rejected=0,
                validation_errors=[
                    CSVRowValidationError(
                        row_number=0,
                        field="file",
                        error=f"Unable to decode CSV file encoding: {str(e)}"
                    )
                ],
                message="File decoding failed. Please upload a UTF-8 encoded CSV."
            )

    reader = csv.reader(text_stream)
    try:
        header = next(reader)
    except StopIteration:
        return CSVUploadResponse(
            filename=filename,
            rows_received=0,
            rows_inserted=0,
            rows_rejected=0,
            validation_errors=[
                CSVRowValidationError(row_number=0, field="header", error="Uploaded CSV is empty.")
            ],
            message="CSV is empty."
        )

    # Normalize header column names
    header_clean = [col.strip().lower() for col in header]
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in header_clean]
    if missing_cols:
        return CSVUploadResponse(
            filename=filename,
            rows_received=0,
            rows_inserted=0,
            rows_rejected=0,
            validation_errors=[
                CSVRowValidationError(
                    row_number=1,
                    field="header",
                    error=f"Missing required columns: {', '.join(missing_cols)}"
                )
            ],
            message=f"Missing required columns: {', '.join(missing_cols)}"
        )

    col_idx = {col: header_clean.index(col) for col in REQUIRED_COLUMNS}

    # Fetch valid route IDs to prevent foreign key violations
    valid_route_ids = set(r[0] for r in db.query(Route.id).all())

    # Cache existing dates in DB per route to check duplicates
    existing_records = db.query(FreightRate.route_id, FreightRate.rate_date).all()
    existing_db_keys = set((r[0], r[1]) for r in existing_records)

    seen_batch_keys = set()
    valid_instances: List[FreightRate] = []
    errors: List[CSVRowValidationError] = []
    total_received = 0

    for row_num, row in enumerate(reader, start=2):
        if not row or all(not cell.strip() for cell in row):
            continue  # Skip blank lines

        total_received += 1
        row_has_error = False

        # Verify row length matches header
        if len(row) < len(header_clean):
            errors.append(CSVRowValidationError(
                row_number=row_num,
                field="row",
                error=f"Incomplete row (expected {len(header_clean)} columns, got {len(row)})",
                value=",".join(row)
            ))
            continue

        route_id_val = row[col_idx["route_id"]].strip()
        rate_date_val = row[col_idx["rate_date"]].strip()
        spot_rate_val = row[col_idx["spot_rate"]].strip()
        currency_val = row[col_idx["currency"]].strip().upper() or "USD"
        unit_val = row[col_idx["unit"]].strip().upper() or "MT"
        data_source_val = row[col_idx["data_source"]].strip() or "CSV Upload"

        # 1. Route validation
        if not route_id_val:
            errors.append(CSVRowValidationError(
                row_number=row_num, field="route_id", error="route_id cannot be empty"
            ))
            row_has_error = True
        elif valid_route_ids and route_id_val not in valid_route_ids:
            errors.append(CSVRowValidationError(
                row_number=row_num, field="route_id",
                error=f"Route ID '{route_id_val}' does not exist in routes registry",
                value=route_id_val
            ))
            row_has_error = True

        # 2. Date validation
        parsed_date: Optional[date] = None
        if not rate_date_val:
            errors.append(CSVRowValidationError(
                row_number=row_num, field="rate_date", error="rate_date cannot be empty"
            ))
            row_has_error = True
        else:
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
                try:
                    parsed_date = datetime.strptime(rate_date_val, fmt).date()
                    break
                except ValueError:
                    continue
            if parsed_date is None:
                errors.append(CSVRowValidationError(
                    row_number=row_num, field="rate_date",
                    error="Invalid date format (must be YYYY-MM-DD or DD-MM-YYYY)",
                    value=rate_date_val
                ))
                row_has_error = True

        # 3. Numeric Spot Rate validation
        parsed_rate: Optional[float] = None
        if not spot_rate_val:
            errors.append(CSVRowValidationError(
                row_number=row_num, field="spot_rate", error="spot_rate cannot be empty"
            ))
            row_has_error = True
        else:
            try:
                # Remove possible currency symbols or commas
                cleaned_num = spot_rate_val.replace("$", "").replace(",", "").strip()
                parsed_rate = float(cleaned_num)
                if parsed_rate <= 0:
                    errors.append(CSVRowValidationError(
                        row_number=row_num, field="spot_rate",
                        error="spot_rate must be a positive number (> 0)",
                        value=spot_rate_val
                    ))
                    row_has_error = True
            except ValueError:
                errors.append(CSVRowValidationError(
                    row_number=row_num, field="spot_rate",
                    error="spot_rate must be numeric",
                    value=spot_rate_val
                ))
                row_has_error = True

        # 4. Duplicate Check
        if not row_has_error and parsed_date is not None:
            key = (route_id_val, parsed_date)
            if key in seen_batch_keys:
                errors.append(CSVRowValidationError(
                    row_number=row_num, field="rate_date",
                    error=f"Duplicate record for route '{route_id_val}' on date '{parsed_date}' within this upload batch",
                    value=rate_date_val
                ))
                row_has_error = True
            elif key in existing_db_keys:
                errors.append(CSVRowValidationError(
                    row_number=row_num, field="rate_date",
                    error=f"Record already exists in database for route '{route_id_val}' on date '{parsed_date}'",
                    value=rate_date_val
                ))
                row_has_error = True
            else:
                seen_batch_keys.add(key)

        if not row_has_error and parsed_date is not None and parsed_rate is not None:
            valid_instances.append(FreightRate(
                route_id=route_id_val,
                rate_date=parsed_date,
                spot_rate=parsed_rate,
                currency=currency_val,
                unit=unit_val,
                data_source=data_source_val,
                is_simulated=False  # Uploaded data is external/user-provided
            ))

    # Commit only valid instances
    rows_inserted = 0
    if valid_instances:
        db.add_all(valid_instances)
        db.commit()
        rows_inserted = len(valid_instances)

    rows_rejected = total_received - rows_inserted

    msg = f"Processed {total_received} rows: {rows_inserted} inserted successfully, {rows_rejected} rejected."

    return CSVUploadResponse(
        filename=filename,
        rows_received=total_received,
        rows_inserted=rows_inserted,
        rows_rejected=rows_rejected,
        validation_errors=errors,
        message=msg
    )
