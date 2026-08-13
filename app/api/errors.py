"""Mapeia falhas do pipeline de sync para status HTTP explícitos."""

from fastapi import HTTPException, status
from pydantic import ValidationError

from app.services.datajud_client import (
    DataJudError,
    DataJudNotFoundError,
    DataJudTransientError,
)


def http_exception_from_sync_error(error: Exception) -> HTTPException:
    """Converte exceção de domínio em HTTPException sem vazar stack ao cliente."""
    if isinstance(error, DataJudNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Processo não encontrado na origem DataJud.",
        )
    if isinstance(error, DataJudTransientError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DataJud temporariamente indisponível. Tente novamente mais tarde.",
        )
    if isinstance(error, DataJudError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Falha ao consultar o DataJud.",
        )
    if isinstance(error, ValidationError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Dados do processo inválidos após normalização.",
        )
    if isinstance(error, ValueError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error) or "Requisição inválida para sincronização.",
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Erro interno ao sincronizar processo. Tente novamente mais tarde.",
    )
