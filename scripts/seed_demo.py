"""
Popula a base local com processos de demonstração (modo mock).

Usa o motor mock determinístico do JurisSync (sem DATAJUD_API_KEY).
Não substitui o teste com DataJud real - veja juris-sync-web/docs/guia-do-testador.md.

Execute na raiz do projeto, com o venv ativo:

    python scripts/seed_demo.py
"""

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import delete

from app.core.cnj import TRIBUNAL_TO_UF
from app.core.database import SessionLocal
from app.models.process import Movimentacao, Processo
from app.services.sync_service import JurisSyncService

# UF -> código TR (Justiça Estadual 8.xx). Cobre os 27 estados + DF.
UF_TR: dict[str, str] = {
    "AC": "01",
    "AL": "02",
    "AP": "03",
    "AM": "04",
    "BA": "05",
    "CE": "06",
    "DF": "07",
    "ES": "08",
    "GO": "09",
    "MA": "10",
    "MT": "11",
    "MS": "12",
    "MG": "13",
    "PA": "14",
    "PB": "15",
    "PR": "16",
    "PE": "17",
    "PI": "18",
    "RJ": "19",
    "RN": "20",
    "RS": "21",
    "RO": "22",
    "RR": "23",
    "SC": "24",
    "SE": "25",
    "SP": "26",
    "TO": "27",
}

# Volumes assimétricos por UF para o choropleth do dashboard ficar legível.
UF_VOLUMES: dict[str, int] = {
    "SP": 15,
    "RJ": 12,
    "MG": 10,
    "BA": 8,
    "PR": 7,
    "RS": 6,
    "SC": 5,
    "PE": 5,
    "CE": 5,
    "GO": 4,
    "PA": 4,
    "DF": 4,
    "ES": 3,
    "MT": 3,
    "MS": 3,
    "MA": 3,
    "PB": 3,
    "RN": 3,
    "AL": 2,
    "PI": 2,
    "SE": 2,
    "AM": 2,
    "AC": 1,
    "AP": 1,
    "RO": 1,
    "RR": 1,
    "TO": 1,
}


def build_demo_cnj(seq: int, tr: str, year: int = 2023) -> str:
    """Gera CNJ único no formato NNNNNNN-DD.AAAA.8.TR.OOOO (mock/demo)."""
    nnnnnnn = f"{seq:07d}"
    dd = f"{(seq * 7 + int(tr)) % 97:02d}"
    orgao = f"{(seq % 9999) + 1:04d}"
    return f"{nnnnnnn}-{dd}.{year}.8.{tr}.{orgao}"


def build_demo_processos() -> list[tuple[str, int]]:
    processos: list[tuple[str, int]] = []
    seq = 1

    for uf in sorted(UF_VOLUMES, key=lambda key: UF_VOLUMES[key], reverse=True):
        tr = UF_TR[uf]
        volume = UF_VOLUMES[uf]
        for index in range(volume):
            year = 2022 + (index % 3)
            grau = 1 if index % 4 else 2
            processos.append((build_demo_cnj(seq, tr, year), grau))
            seq += 1

    return processos


DEMO_PROCESSOS = build_demo_processos()


async def clear_demo_data() -> None:
    async with SessionLocal() as db:
        await db.execute(delete(Movimentacao))
        await db.execute(delete(Processo))
        await db.commit()
    print("Base limpa (processos e movimentações removidos).\n")


async def main(fresh: bool = False) -> None:
    if fresh:
        await clear_demo_data()

    uf_counter: Counter[str] = Counter()

    async with SessionLocal() as db:
        service = JurisSyncService(db)

        for numero_cnj, grau in DEMO_PROCESSOS:
            resultado = await service.sync_process(numero_cnj, grau)
            processo = resultado["processo"]
            uf = TRIBUNAL_TO_UF.get(processo.tribunal.upper())
            if uf:
                uf_counter[uf] += 1
            print(
                f"OK {numero_cnj} -> {processo.tribunal} ({uf or '?'}) | "
                f"{processo.assunto} | {resultado['movimentacoes_sincronizadas']} mov."
            )

    print(f"\nConcluído: {len(DEMO_PROCESSOS)} processos na base de demo.")
    print("\nTotais por UF:")
    for uf, total in uf_counter.most_common():
        print(f"  {uf}: {total}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Popula a base com processos mock de demo.")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Remove processos existentes antes de popular (evita misturar seeds antigos).",
    )
    args = parser.parse_args()
    asyncio.run(main(fresh=args.fresh))
