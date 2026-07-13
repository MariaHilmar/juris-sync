import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Processo(Base):
    __tablename__ = "processos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Número CNJ único (ex: 0000000-00.0000.0.00.0000)
    numero_cnj: Mapped[str] = mapped_column(
        String(25), unique=True, index=True, nullable=False
    )
    classe: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    assunto: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tribunal: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    orgao_julgador: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    data_distribuicao: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    data_ultima_atualizacao: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False
    )
    grau: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relacionamento de 1-N com Movimentações
    # Sempre ordenado da mais recente para a mais antiga por padrão
    movimentacoes: Mapped[List["Movimentacao"]] = relationship(
        "Movimentacao",
        back_populates="processo",
        cascade="all, delete-orphan",
        order_by="desc(Movimentacao.data_hora)",
    )

    def __repr__(self) -> str:
        return f"<Processo cnj={self.numero_cnj} tribunal={self.tribunal}>"


class Movimentacao(Base):
    __tablename__ = "movimentacoes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    processo_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processos.id", ondelete="CASCADE"), index=True, nullable=False
    )
    data_hora: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    complemento: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    codigo_movimento: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relacionamento reverso
    processo: Mapped["Processo"] = relationship(
        "Processo", back_populates="movimentacoes"
    )

    def __repr__(self) -> str:
        return f"<Movimentacao processo_id={self.processo_id} data_hora={self.data_hora} descricao={self.descricao[:30]}>"
