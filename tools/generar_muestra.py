"""Genera planillas de prueba. Uso: python tools/generar_muestra.py 50000 salida.csv [--errores 0.02] [--xlsx]"""
import argparse
import csv
import random
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

NOMBRES = ["Carlos", "Maria", "Jose", "Ana", "Luis", "Rosa", "Pedro", "Lucia", "Miguel", "Elena"]
APELLIDOS = ["Gonzalez", "Rodriguez", "Perez", "Martinez", "Castillo", "Sanchez", "De Leon", "Batista"]
q = lambda x: x.quantize(Decimal("0.01"), ROUND_HALF_UP)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", type=int)
    ap.add_argument("salida")
    ap.add_argument("--errores", type=float, default=0.02, help="fraccion de filas con errores")
    ap.add_argument("--xlsx", action="store_true")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    random.seed(a.seed)
    filas = [["cedula", "nss", "nombres", "apellidos", "fecha_ingreso", "salario", "descuento_css", "descuento_se"]]
    for i in range(a.n):
        prov, tomo, asiento = random.randint(1, 9), random.randint(1, 999), i + 1000
        sal = Decimal(random.randint(500, 4500))
        fila = [f"{prov}-{tomo}-{asiento}", str(10_000_000 + i), random.choice(NOMBRES), random.choice(APELLIDOS),
                (date(2015, 1, 1) + timedelta(days=random.randint(0, 3000))).isoformat(), str(sal),
                str(q(sal * Decimal("0.0975"))), str(q(sal * Decimal("0.0125")))]
        if random.random() < a.errores:
            tipo = random.choice(["ced", "dup", "sal", "css", "fecha", "nom"])
            if tipo == "ced": fila[0] = "8-ABC"
            elif tipo == "dup" and i: fila[0] = filas[random.randint(1, i)][0]
            elif tipo == "sal": fila[5] = "mil quinientos"
            elif tipo == "css": fila[6] = str(q(sal * Decimal("0.10")))
            elif tipo == "fecha": fila[4] = "31/02/2020"
            elif tipo == "nom": fila[2] = ""
        filas.append(fila)
    if a.xlsx:
        from openpyxl import Workbook
        wb = Workbook(write_only=True)
        ws = wb.create_sheet()
        for f in filas: ws.append(f)
        wb.save(a.salida)
    else:
        with open(a.salida, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(filas)
    print(f"{a.n} registros -> {a.salida}")


if __name__ == "__main__":
    main()
