"""Lista quién comentó INFO en los posts de los últimos 7 días (para escribirles a mano).

Imprime una sección en Markdown; si no hay token de Threads, no imprime nada.
"""
import os
import re
import time

from threads import Threads

DIAS = 7
PALABRA = re.compile(r"\binfo\b", re.IGNORECASE)


def main():
    if not os.environ.get("THREADS_ACCESS_TOKEN"):
        return
    api = Threads()
    pedidos = []
    for post in api.posts_desde(int(time.time()) - DIAS * 86400):
        for r in api.respuestas(post["id"]):
            if PALABRA.search(r.get("text", "")) and r.get("username") != api.usuario["username"]:
                pedidos.append(r)

    print("\n### Comentaron INFO (últimos 7 días)\n")
    if not pedidos:
        print("Nadie por ahora.")
        return
    for r in sorted(pedidos, key=lambda r: r["timestamp"], reverse=True):
        enlace = r.get("permalink") or ""
        print(f"- [ ] **@{r['username']}** · {r['timestamp'][:10]} · \"{r.get('text', '').strip()[:80]}\" {enlace}")
    print("\nMarcá cada casilla cuando le hayas escrito.")


if __name__ == "__main__":
    main()
