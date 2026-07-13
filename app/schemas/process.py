import re
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

# ----------------------------------------
# Schemas de Movimentação
# ----------------------------------------


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

    class Config:
        from_attributes = True


# ----------------------------------------
# Schemas de Processo
# ----------------------------------------


class ProcessoBase(BaseModel):
    numero_cnj: str = Field(
        ...,
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
        # Regex para validar o formato CNJ: NNNNNNN-DD.YYYY.J.TR.OOOO
        pattern = r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$"
        if not re.match(pattern, value):
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

    class Config:
        from_attributes = True


# Schema completo que inclui as movimentações do processo ordenadas
class ProcessoDetailRead(ProcessoRead):
    movimentacoes: List[MovimentacaoRead] = []

    class Config:
        from_attributes = True


# ----------------------------------------
# Schemas de Requisição / Resposta de Sync
# ----------------------------------------


class ProcessoSyncRequest(BaseModel):
    numero_cnj: str = Field(..., description="Número do processo no padrão CNJ")
    grau: int = Field(1, ge=1, le=3, description="Grau de jurisdição do processo")

    @field_validator("numero_cnj")
    @classmethod
    def validar_numero_cnj(cls, value: str) -> str:
        pattern = r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$"
        if not re.match(pattern, value):
            raise ValueError("Formato de número CNJ inválido.")
        return value


class ProcessoSyncResponse(BaseModel):
    sucesso: bool
    mensagem: str
    processo: Optional[ProcessoRead] = None
    movimentacoes_sincronizadas: int = 0
