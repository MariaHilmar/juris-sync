from fastapi import status
from pydantic import ValidationError

from app.api.errors import http_exception_from_sync_error
from app.schemas.datajud import DataJudProcessoSchema
from app.services.datajud_client import (
    DataJudError,
    DataJudNotFoundError,
    DataJudTransientError,
)


def test_maps_not_found_to_404():
    mapped = http_exception_from_sync_error(DataJudNotFoundError("ausente"))
    assert mapped.status_code == status.HTTP_404_NOT_FOUND


def test_maps_transient_to_503():
    mapped = http_exception_from_sync_error(DataJudTransientError("timeout"))
    assert mapped.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


def test_maps_datajud_error_to_502():
    mapped = http_exception_from_sync_error(DataJudError("http 400"))
    assert mapped.status_code == status.HTTP_502_BAD_GATEWAY


def test_maps_validation_error_to_422():
    try:
        DataJudProcessoSchema.from_enriched({"numero_cnj": "x", "tribunal": "TJSP"})
    except ValidationError as error:
        mapped = http_exception_from_sync_error(error)
    assert mapped.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_maps_value_error_to_400():
    mapped = http_exception_from_sync_error(ValueError("Tribunal não mapeado"))
    assert mapped.status_code == status.HTTP_400_BAD_REQUEST


def test_maps_unknown_to_500():
    mapped = http_exception_from_sync_error(RuntimeError("boom"))
    assert mapped.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
