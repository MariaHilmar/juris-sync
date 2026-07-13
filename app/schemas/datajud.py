import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class DataJudMovimentacaoSchema(BaseModel):
    data_hora: datetime = Field(
        ..., description="Data e hora da movimentação processual"
    )
    descricao: str = Field(
        ..., min_length=1, description="Descrição do andamento processual"
    )
    complemento: Optional[str] = Field(None, description="Complemento da movimentação")
    codigo_movimento: Optional[int] = Field(
        None, description="Código CNJ da movimentação"
    )


class DataJudProcessoSchema(BaseModel):
    numero_cnj: str = Field(..., description="Número do processo no padrão CNJ")
    classe: Optional[str] = Field(None, description="Classe processual normalizada")
    assunto: Optional[str] = Field(None, description="Assunto jurídico normalizado")
    tribunal: str = Field(..., min_length=2, description="Sigla do tribunal")
    orgao_julgador: Optional[str] = Field(
        None, description="Órgão julgador responsável"
    )
    data_distribuicao: Optional[datetime] = Field(
        None, description="Data de distribuição"
    )
    grau: int = Field(1, ge=1, le=3, description="Grau de jurisdição")
    movimentacoes: List[DataJudMovimentacaoSchema] = Field(default_factory=list)
    contexto_rag: List[str] = Field(
        default_factory=list,
        description="Trechos de conhecimento jurídico recuperados pelo RAG",
    )

    @field_validator("numero_cnj")
    @classmethod
    def validar_numero_cnj(cls, value: str) -> str:
        pattern = r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$"
        if not re.match(pattern, value):
            raise ValueError(
                "O número CNJ fornecido está em formato inválido. "
                "Use o padrão NNNNNNN-DD.YYYY.J.TR.OOOO"
            )
        return value

    @classmethod
    def from_enriched(cls, enriched: dict) -> "DataJudProcessoSchema":
        return cls.model_validate(enriched)
