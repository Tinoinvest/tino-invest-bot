"""Publica en Threads el post de una fecha (los slides ya tienen que estar subidos al repo).

Uso: python bot/publicar.py AAAA-MM-DD
"""
import json
import os
import sys
from pathlib import Path

from threads import Threads

RAIZ = Path(__file__).resolve().parent.parent


def main():
    fecha = sys.argv[1]
    carpeta = RAIZ / "posts" / fecha
    destino = carpeta / "publicado.json"
    if destino.exists():
        raise SystemExit(f"El post del {fecha} ya estaba publicado: {json.loads(destino.read_text())['permalink']}")

    post = json.loads((carpeta / "post.json").read_text(encoding="utf-8"))
    repo = os.environ["GITHUB_REPOSITORY"]
    base = f"https://raw.githubusercontent.com/{repo}/main/posts/{fecha}"
    urls = [f"{base}/slide-{i}.png" for i in range(1, len(post["slides"]) + 1)]

    resultado = Threads().publicar_carrusel(post["texto"], urls)
    destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Publicado: {resultado['permalink']}")

    salida = os.environ.get("GITHUB_OUTPUT")
    if salida:
        with open(salida, "a", encoding="utf-8") as f:
            f.write(f"permalink={resultado['permalink']}\n")


if __name__ == "__main__":
    main()
