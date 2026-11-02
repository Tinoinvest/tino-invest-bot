"""Convierte un post (post.json) en slides PNG con la plantilla de la marca."""
import json
import re
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup, escape
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parent.parent
PLANTILLAS = RAIZ / "plantilla"


def negritas(texto):
    """Escapa el texto y convierte **así** en negrita."""
    seguro = str(escape(texto))
    return Markup(re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", seguro))


def armar_html(post):
    env = Environment(loader=FileSystemLoader(PLANTILLAS), autoescape=True)
    env.filters["negritas"] = negritas
    return env.get_template("carrusel.html.j2").render(post=post, total=len(post["slides"]))


def renderizar(post, carpeta, canal_chrome=None):
    """Genera slide-1.png ... slide-N.png en `carpeta`.

    Devuelve (rutas, desbordes): desbordes es la lista de slides cuyo contenido no entró.
    """
    carpeta.mkdir(parents=True, exist_ok=True)
    html = carpeta / "carrusel.html"
    html.write_text(armar_html(post), encoding="utf-8")

    rutas = []
    with sync_playwright() as p:
        navegador = p.chromium.launch(channel=canal_chrome) if canal_chrome else p.chromium.launch()
        pagina = navegador.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)
        pagina.goto(html.resolve().as_uri())
        pagina.wait_for_function("window.__listo === true", timeout=20000)
        desbordes = pagina.evaluate("window.__desbordes")
        for i, slide in enumerate(pagina.locator(".slide").all(), start=1):
            ruta = carpeta / f"slide-{i}.png"
            slide.screenshot(path=str(ruta))
            rutas.append(ruta)
        navegador.close()
    return rutas, desbordes


if __name__ == "__main__":
    # uso: python bot/render.py posts/2026-11-03/post.json [chrome]
    archivo = Path(sys.argv[1])
    canal = sys.argv[2] if len(sys.argv) > 2 else None
    rutas, desbordes = renderizar(json.loads(archivo.read_text(encoding="utf-8")), archivo.parent, canal)
    print(f"{len(rutas)} slides en {archivo.parent}")
    if desbordes:
        print(f"Atención: no entra el contenido en los slides {desbordes}")
