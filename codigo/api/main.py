import os
import psycopg

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Nutresa API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

DATABASE_URL = os.getenv("DATABASE_URL")


def get_db():
    return psycopg.connect(DATABASE_URL)


@app.get("/")
def inicio():
    return {
        "empresa": "Grupo Nutresa",
        "servicio": "Backend API",
        "estado": "Funcionando"
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/productos")
def productos():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS productos (
                    id SERIAL PRIMARY KEY,
                    nombre VARCHAR(100) NOT NULL
                )
            """)

            cur.execute("""
                SELECT id, nombre FROM productos
            """)

            resultados = cur.fetchall()

    return [
        {"id": fila[0], "nombre": fila[1]}
        for fila in resultados
    ]


@app.post("/productos")
def crear_producto(producto: dict):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO productos (nombre) VALUES (%s) RETURNING id",
                (producto["nombre"],)
            )
            nuevo_id = cur.fetchone()[0]

    return {
        "id": nuevo_id,
        "nombre": producto["nombre"]
    }