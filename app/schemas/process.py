import re
import uuid
from datetime import UTC, datetime
from typing import List, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
)

# ----------------------------------------
# Schemas de Movimentação
# ----------------------------------------


def _garantir_utc(value: Optional[datetime]) -> Optional[datetime]:
    """
    Garante que toda data/hora exposta pela API seja timezone-aware (RFC3339
    / "date-time" do OpenAPI). O SQLite (usado em desenvolvimento e testes)
    não preserva timezone mesmo em colunas DateTime(timezone=True), o que
    quebraria o contrato documentado no schema OpenAPI em produção contra
    PostgreSQL. Datas ingênuas são tratadas como UTC.
    """
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class MovimentacaoBase(BaseModel):
    data_hora: datetime = Field(
        ..., description="Data e hora da movimentação processual"
    )
    descricao: str = Field(
        ..., min_length=1, description="Descrição clara do andamento processual"
    )
    complemento: Optional[str] = Field(
        None, description="Detalhes adicionais ou complemento da movimentação"
    )
    codigo_movimento: Optional[int] = Field(
        None, description="Código de movimento padronizado pelo CNJ"
    )


class MovimentacaoCreate(MovimentacaoBase):
    pass


class MovimentacaoRead(MovimentacaoBase):
    id: uuid.UUID
    processo_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("data_hora", "created_at")
    def _serializar_utc(self, value: datetime) -> datetime:
        result = _garantir_utc(value)
        assert result is not None
        return result


# ----------------------------------------
# Schemas de Processo
# ----------------------------------------


# Usa [0-9] em vez de \d: em Python, \d é Unicode-aware por padrão e também
# casa dígitos de outros alfabetos (ex: devanágari, tâmil), o que diverge da
# semântica ASCII-only assumida por validadores de JSON Schema de terceiros
# (ex: Schemathesis/jsonschema-rs). Isso causava um número CNJ aceito pela
# validação Pydantic mas rejeitado como não-conforme ao contrato OpenAPI.
CNJ_PATTERN = r"^[0-9]{7}-[0-9]{2}\.[0-9]{4}\.[0-9]\.[0-9]{2}\.[0-9]{4}$"


class ProcessoBase(BaseModel):
    numero_cnj: str = Field(
        ...,
        pattern=CNJ_PATTERN,
        description="Número único do processo no padrão CNJ (ex: 0000000-00.0000.0.00.0000)",
    )
    classe: Optional[str] = Field(
        None, description="Classe processual (ex: Procedimento Comum Cível)"
    )
    assunto: Optional[str] = Field(
        None, description="Assunto principal (ex: Dano Moral)"
    )
    tribunal: str = Field(..., description="Sigla do tribunal (ex: TJPB, TJSP, TRF1)")
    orgao_julgador: Optional[str] = Field(
        None, description="Órgão Julgador responsável"
    )
    data_distribuicao: Optional[datetime] = Field(
        None, description="Data de distribuição do processo"
    )
    grau: int = Field(
        1, ge=1, le=3, description="Grau de jurisdição do processo (1, 2 ou 3)"
    )

    @field_validator("numero_cnj")
    @classmethod
    def validar_numero_cnj(cls, value: str) -> str:
        if not re.match(CNJ_PATTERN, value):
            raise ValueError(
                "O número CNJ fornecido está em formato inválido. Use o padrão NNNNNNN-DD.YYYY.J.TR.OOOO"
            )
        return value


class ProcessoCreate(ProcessoBase):
    pass


class ProcessoRead(ProcessoBase):
    id: uuid.UUID
    data_ultima_atualizacao: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer(
        "data_distribuicao", "data_ultima_atualizacao", "created_at", "updated_at"
    )
    def _serializar_utc(self, value: Optional[datetime]) -> Optional[datetime]:
        return _garantir_utc(value)


# Schema completo que inclui as movimentações do processo ordenadas
class ProcessoDetailRead(ProcessoRead):
    movimentacoes: List[MovimentacaoRead] = []


class ProcessoListResponse(BaseModel):
    """Resposta paginada da listagem de processos locais."""

    items: List[ProcessoRead] = Field(
        default_factory=list, description="Página de processos retornada"
    )
    total: int = Field(
        ..., ge=0, description="Total de registros que atendem aos filtros aplicados"
    )
    limit: int = Field(..., ge=1, le=100, description="Tamanho máximo da página")
    offset: int = Field(..., ge=0, description="Deslocamento da paginação")


# ----------------------------------------
# Schemas de Requisição / Resposta de Sync
# ----------------------------------------


class ProcessoSyncRequest(BaseModel):
    numero_cnj: str = Field(
        ..., pattern=CNJ_PATTERN, description="Número do processo no padrão CNJ"
    )
    grau: int = Field(1, ge=1, le=3, description="Grau de jurisdição do processo")

    @field_validator("numero_cnj")
    @classmethod
    def validar_numero_cnj(cls, value: str) -> str:
        if not re.match(CNJ_PATTERN, value):
            raise ValueError("Formato de número CNJ inválido.")
        return value


class ProcessoSyncResponse(BaseModel):
    sucesso: bool
    mensagem: str
    processo: Optional[ProcessoRead] = None
    movimentacoes_sincronizadas: int = 0
