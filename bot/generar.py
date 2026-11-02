"""Genera el post del día: elige el tema, investiga con búsqueda web, escribe el texto y arma los slides.

Dos formas de usarlo:
- Con la API (pago por uso):   python bot/generar.py [AAAA-MM-DD]
- Con la suscripción de Claude (Claude Code hace la investigación y escribe post.json):
    python bot/generar.py --preparar [AAAA-MM-DD]   -> instrucciones para Claude Code
    python bot/generar.py --validar AAAA-MM-DD      -> revisa post.json
    python bot/generar.py --terminar [AAAA-MM-DD]   -> slides, historial e issue
Deja todo en posts/<fecha>/ (post.json, slides PNG, issue.md) y actualiza posts/historial.json.
"""
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic

from render import renderizar

RAIZ = Path(__file__).resolve().parent.parent
POSTS = RAIZ / "posts"
HISTORIAL = POSTS / "historial.json"

MODELO = "claude-opus-5-5"
# Si el modelo rechaza un pedido, la API lo reintenta sola con otro modelo.
BETA_FALLBACK = "server-side-fallback-2026-07-01"
LIMITE_THREADS = 500  # caracteres máximos de un post en Threads

PILARES = {
    0: "El dato de la semana",
    1: "Primera inversión",
    2: "Barrios y ciudades",
    3: "Hagamos la cuenta",
    4: "Errores y mitos",
    5: None,  # sábado: alterna según la semana
    6: "Pregunta abierta",
}

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

TIPOS_SLIDE = ["portada", "numero", "cuenta", "destacado", "lista", "cierre"]

ESQUEMA_POST = {
    "type": "object",
    "properties": {
        "tema": {"type": "string"},
        "texto": {"type": "string"},
        "fuente": {"type": "string"},
        "slides": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tipo": {"type": "string", "enum": TIPOS_SLIDE},
                    "kicker": {"type": "string"},
                    "titulo": {"type": "string"},
                    "prefijo": {"type": "string"},
                    "valor": {"type": "string"},
                    "unidad": {"type": "string"},
                    "etiqueta": {"type": "string"},
                    "operacion": {"type": "string"},
                    "resultado": {"type": "string"},
                    "texto": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"etiqueta": {"type": "string"}, "valor": {"type": "string"}},
                            "required": ["etiqueta", "valor"],
                            "additionalProperties": False,
                        },
                    },
                    "barras": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "etiqueta": {"type": "string"},
                                "valor_texto": {"type": "string"},
                                "valor_num": {"type": "number"},
                            },
                            "required": ["etiqueta", "valor_texto", "valor_num"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["tipo", "kicker", "titulo", "prefijo", "valor", "unidad", "etiqueta",
                             "operacion", "resultado", "texto", "items", "barras"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["tema", "texto", "fuente", "slides"],
    "additionalProperties": False,
}

GUIA_SLIDES = """Tipos de slide (completá solo los campos que usa cada tipo; el resto va como "" o []):
- portada: kicker (2-4 palabras, ej. "Asunción · Monoambiente"), titulo (pregunta o gancho, máx. 40 caracteres), texto (bajada corta, máx. 40).
- numero: kicker, prefijo opcional (ej. "USD"), valor (el número, máx. 8 caracteres, ej. "75.000"), unidad opcional (ej. "%"), texto (1-2 frases, máx. 110 caracteres; podés usar **negrita**).
- cuenta: kicker, valor (número de partida), etiqueta (qué es ese número), operacion (ej. "× 12 meses"), resultado (máx. 8 caracteres), texto (máx. 60).
- destacado: fondo verde oscuro, para EL número clave del post. kicker, valor, unidad, texto (máx. 110).
- lista: kicker, items (2 a 4 filas {etiqueta, valor}, etiqueta máx. 28 caracteres), etiqueta (rótulo del resultado, ej. "Te queda neto"), resultado (máx. 7 caracteres).
- cierre: SIEMPRE el último. kicker, barras opcionales (2 o 3 comparaciones {etiqueta, valor_texto, valor_num}), titulo (frase final, máx. 45 caracteres), texto opcional. El botón "Comentá INFO y te escribo" lo agrega la plantilla solo.

Reglas del carrusel: entre 5 y 7 slides. El primero es "portada" y el último "cierre". Usá como mucho un "destacado".
El kicker de los pasos puede ir numerado ("Paso 1 · Lo que cuesta") cuando el post es una cuenta.
Los números van con formato paraguayo: punto de miles y coma decimal (75.000 · 8,8%)."""


def leer(nombre):
    return (RAIZ / nombre).read_text(encoding="utf-8")


def pilar_del_dia(fecha):
    pilar = PILARES[fecha.weekday()]
    if pilar is None:
        semana = fecha.isocalendar().week
        pilar = "Hagamos la cuenta" if semana % 2 == 0 else "Paraguay vs. la región"
    return pilar


def temas_recientes(fecha, dias=42):
    if not HISTORIAL.exists():
        return []
    desde = fecha - dt.timedelta(days=dias)
    historial = json.loads(HISTORIAL.read_text(encoding="utf-8"))
    return [h for h in historial if dt.date.fromisoformat(h["fecha"]) >= desde]


def llamar(cliente, **kwargs):
    """Llama a la API con fallback del lado del servidor y corta si el pedido fue rechazado."""
    respuesta = cliente.beta.messages.create(
        model=MODELO,
        betas=[BETA_FALLBACK],
        extra_body={"fallbacks": "default"},
        **kwargs,
    )
    if respuesta.stop_reason == "refusal":
        raise SystemExit("El modelo rechazó el pedido. Revisá el tema del día.")
    return respuesta


def investigar(cliente, fecha, pilar, recientes):
    """Paso 1: elige el tema y busca datos actuales en la web. Devuelve un resumen con fuentes."""
    sistema = (
        "Sos el investigador de @tino.invest, una cuenta educativa de inversión inmobiliaria en Paraguay. "
        "Tu trabajo es elegir el tema del post de hoy y juntar datos reales y actuales, con su fuente. "
        "Nunca inventes cifras: si no encontrás un dato confiable, decilo y proponé un rango razonable "
        "marcado como estimación, o un enfoque conceptual que no dependa de ese número. "
        "Preferí fuentes paraguayas serias: BCP, INE, DNIT, MUVH, diarios (ABC, La Nación, Última Hora, 5días), "
        "portales inmobiliarios e informes de cámaras del sector.\n\n"
        f"Calendario y banco de temas:\n{leer('TEMAS.md')}"
    )
    lista_recientes = "\n".join(f"- {h['fecha']}: {h['tema']}" for h in recientes) or "- (ninguno todavía)"
    pedido = (
        f"Hoy es {fecha.isoformat()} ({DIAS[fecha.weekday()]}). Pilar del día: **{pilar}**.\n\n"
        f"Temas ya publicados en las últimas 6 semanas (no los repitas):\n{lista_recientes}\n\n"
        "1. Elegí un tema del banco para este pilar (o uno nuevo que encaje, si es más oportuno por una noticia).\n"
        "2. Buscá en la web los datos que hacen falta para explicarlo con números simples.\n"
        "3. Respondé con un resumen de investigación: el tema elegido, los datos clave (cada uno con su fuente y fecha), "
        "y una propuesta de cuenta paso a paso si aplica. Indicá qué cifras son estimaciones."
    )
    mensajes = [{"role": "user", "content": pedido}]
    herramientas = [{
        "type": "web_search_20260209",
        "name": "web_search",
        "max_uses": 8,
        "user_location": {"type": "approximate", "country": "PY", "city": "Asunción", "timezone": "America/Asuncion"},
    }]

    for _ in range(5):
        respuesta = llamar(cliente, max_tokens=16000, system=sistema, tools=herramientas,
                           output_config={"effort": "high"}, messages=mensajes)
        if respuesta.stop_reason != "pause_turn":
            break
        # la búsqueda web pidió más tiempo: se reenvía para que siga
        mensajes = [{"role": "user", "content": pedido}, {"role": "assistant", "content": respuesta.content}]

    return "\n".join(b.text for b in respuesta.content if b.type == "text").strip()


def problemas_del_post(post):
    problemas = []
    largo = len(post["texto"])
    if largo > LIMITE_THREADS:
        problemas.append(f"El texto tiene {largo} caracteres y Threads acepta {LIMITE_THREADS}. Acortalo.")
    if "INFO" not in post["texto"]:
        problemas.append('El texto tiene que terminar con el CTA que pide comentar "INFO".')
    slides = post["slides"]
    if not 5 <= len(slides) <= 7:
        problemas.append(f"Tiene {len(slides)} slides y tienen que ser entre 5 y 7.")
    if slides and slides[0]["tipo"] != "portada":
        problemas.append('El primer slide tiene que ser "portada".')
    if slides and slides[-1]["tipo"] != "cierre":
        problemas.append('El último slide tiene que ser "cierre".')
    if sum(s["tipo"] == "cierre" for s in slides) > 1:
        problemas.append('Solo puede haber un slide "cierre".')
    return problemas


def escribir(cliente, fecha, pilar, investigacion):
    """Paso 2: escribe el texto y los slides con la voz de la marca. Devuelve el post como dict."""
    sistema = (
        "Sos el redactor de @tino.invest. Escribís el post diario para Threads (texto + carrusel) "
        "siguiendo al pie de la letra esta guía de estilo:\n\n"
        f"{leer('GUIA-DE-ESTILO.md')}\n\n{GUIA_SLIDES}\n\n"
        f"El texto del post tiene un máximo estricto de {LIMITE_THREADS} caracteres, CTA incluido. "
        "En el campo fuente poné las fuentes de forma corta para el pie del slide (ej. \"Fuente: BCP, INE\"); "
        "si alguna cifra es estimada, agregá \"· Estimaciones propias\". "
        "Usá solo los datos de la investigación; no agregues cifras nuevas."
    )
    pedido = (
        f"Fecha: {fecha.isoformat()}. Pilar: {pilar}.\n\n"
        f"Investigación del día:\n\n{investigacion}\n\n"
        "Escribí el post (texto + slides)."
    )
    mensajes = [{"role": "user", "content": pedido}]
    formato = {"effort": "high", "format": {"type": "json_schema", "schema": ESQUEMA_POST}}

    for intento in range(3):
        respuesta = llamar(cliente, max_tokens=16000, system=sistema, output_config=formato, messages=mensajes)
        texto = next(b.text for b in respuesta.content if b.type == "text")
        post = json.loads(texto)
        problemas = problemas_del_post(post)
        if not problemas:
            return post
        print(f"Intento {intento + 1}: hay que corregir -> {problemas}")
        mensajes += [
            {"role": "assistant", "content": respuesta.content},
            {"role": "user", "content": "Corregí esto y devolvé el post completo:\n- " + "\n- ".join(problemas)},
        ]
    raise SystemExit(f"No se pudo generar un post válido: {problemas}")


def escribir_issue(carpeta, fecha, post, investigacion, repo):
    base = f"https://raw.githubusercontent.com/{repo}/main/posts/{fecha.isoformat()}"
    imagenes = "\n".join(f'<img src="{base}/slide-{i}.png" width="270">'
                         for i in range(1, len(post["slides"]) + 1))
    cuerpo = (
        f"**Pilar:** {post['pilar']} · **Tema:** {post['tema']}\n\n"
        f"### Texto ({len(post['texto'])}/{LIMITE_THREADS} caracteres)\n\n"
        + "\n".join(f"> {linea}" if linea else ">" for linea in post["texto"].split("\n"))
        + f"\n\n### Slides\n\n{imagenes}\n\n"
        "### ¿Qué hago?\n\n"
        "- Para publicarlo, comentá `/publicar` en este issue.\n"
        "- Para descartarlo, cerrá el issue.\n"
        "- Para cambiar algo, editá `posts/" + fecha.isoformat() + "/post.json` y después comentá `/publicar`: "
        "los slides se vuelven a armar desde ese archivo antes de publicar.\n\n"
        f"<details><summary>Investigación y fuentes</summary>\n\n{investigacion}\n\n</details>\n"
    )
    (carpeta / "issue.md").write_text(cuerpo, encoding="utf-8")


def pedido_claude_code(fecha, pilar, recientes):
    """Instrucciones para Claude Code (modo suscripción): investiga, escribe post.json y lo valida."""
    carpeta = f"posts/{fecha.isoformat()}"
    lista_recientes = "\n".join(f"- {h['fecha']}: {h['tema']}" for h in recientes) or "- (ninguno todavía)"
    return f"""Sos el investigador y redactor de @tino.invest, una cuenta educativa de inversión inmobiliaria en Paraguay.
Hoy es {fecha.isoformat()} ({DIAS[fecha.weekday()]}). Pilar del día: **{pilar}**.

Antes de empezar, leé GUIA-DE-ESTILO.md y TEMAS.md (en la raíz del repo) y seguilos al pie de la letra.

Temas ya publicados en las últimas 6 semanas (no los repitas):
{lista_recientes}

## 1. Investigación
Elegí un tema del banco para este pilar (o uno nuevo que encaje, si es más oportuno por una noticia) y buscá en la web
los datos que hacen falta para explicarlo con números simples. Nunca inventes cifras: si no encontrás un dato confiable,
usá un rango razonable marcado como estimación, o un enfoque conceptual que no dependa de ese número.
Preferí fuentes paraguayas serias: BCP, INE, DNIT, MUVH, diarios (ABC, La Nación, Última Hora, 5días),
portales inmobiliarios e informes de cámaras del sector.
Guardá el resumen en `{carpeta}/investigacion.md`: tema elegido, datos clave con fuente y fecha, y qué cifras son estimaciones.

## 2. Post
Escribí `{carpeta}/post.json` con este esquema JSON exacto (mirá `ejemplos/post-ejemplo.json` como referencia de formato):

```json
{json.dumps(ESQUEMA_POST, ensure_ascii=False)}
```

{GUIA_SLIDES}

- "texto": el post para Threads, máximo estricto de {LIMITE_THREADS} caracteres con el CTA "Comentá INFO" incluido.
- "fuente": fuentes cortas para el pie del slide (ej. "Fuente: BCP, INE"); si alguna cifra es estimada, agregá "· Estimaciones propias".
- Usá solo datos de tu investigación.

## 3. Validación
Corré `python bot/generar.py --validar {fecha.isoformat()}` y corregí `post.json` hasta que diga OK.
No toques ningún otro archivo del repo.
"""


def validar(post):
    """Revisa que post.json respete el esquema y las reglas. Devuelve la lista de problemas."""
    faltan = [c for c in ESQUEMA_POST["required"] if c not in post]
    if faltan:
        return [f"Faltan campos: {faltan}"]
    campos = ESQUEMA_POST["properties"]["slides"]["items"]["required"]
    problemas = []
    for i, s in enumerate(post["slides"], start=1):
        faltan = [c for c in campos if c not in s]
        if faltan:
            problemas.append(f"Al slide {i} le faltan campos: {faltan}")
        if s.get("tipo") not in TIPOS_SLIDE:
            problemas.append(f"El slide {i} tiene un tipo inválido: {s.get('tipo')}")
    return problemas or problemas_del_post(post) or problemas_de_diseno(post)


def problemas_de_diseno(post):
    """Arma los slides en una carpeta temporal y avisa cuáles no entran en el diseño."""
    with tempfile.TemporaryDirectory() as tmp:
        _, desbordes = renderizar(post, Path(tmp), os.environ.get("CANAL_CHROME"))
    return [f"El slide {n} no entra en el diseño: acortá sus textos o sacale elementos "
            "(en el cierre, menos barras o un título más corto)." for n in desbordes]


def terminar(fecha, pilar, post, investigacion):
    """Guarda el post, arma los slides, actualiza el historial y deja listo el issue."""
    carpeta = POSTS / fecha.isoformat()
    post = {"fecha": fecha.isoformat(), "pilar": pilar,
            **{k: v for k, v in post.items() if k not in ("fecha", "pilar")}}
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "post.json").write_text(json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8")
    (carpeta / "investigacion.md").write_text(investigacion, encoding="utf-8")

    rutas, desbordes = renderizar(post, carpeta, os.environ.get("CANAL_CHROME"))
    if desbordes:
        print(f"Atención: revisá los slides {desbordes}, el contenido no entra completo.")

    historial = json.loads(HISTORIAL.read_text(encoding="utf-8")) if HISTORIAL.exists() else []
    historial = [h for h in historial if h["fecha"] != fecha.isoformat()]
    historial.append({"fecha": fecha.isoformat(), "pilar": pilar, "tema": post["tema"]})
    HISTORIAL.write_text(json.dumps(historial, ensure_ascii=False, indent=2), encoding="utf-8")

    escribir_issue(carpeta, fecha, post, investigacion, os.environ.get("GITHUB_REPOSITORY", "usuario/repo"))

    salida = os.environ.get("GITHUB_OUTPUT")
    if salida:
        with open(salida, "a", encoding="utf-8") as f:
            f.write(f"fecha={fecha.isoformat()}\n")
    print(f"Listo: {len(rutas)} slides en {carpeta}")


def main():
    args = sys.argv[1:]
    modo = args.pop(0) if args and args[0].startswith("--") else "--api"
    hoy_py = dt.datetime.now(ZoneInfo("America/Asuncion")).date()
    fecha = dt.date.fromisoformat(args[0]) if args else hoy_py
    pilar = pilar_del_dia(fecha)
    carpeta = POSTS / fecha.isoformat()

    if modo == "--api":
        # Modo API: necesita ANTHROPIC_API_KEY (se paga por uso)
        print(f"Post del {fecha} · pilar: {pilar}")
        cliente = anthropic.Anthropic()
        investigacion = investigar(cliente, fecha, pilar, temas_recientes(fecha))
        terminar(fecha, pilar, escribir(cliente, fecha, pilar, investigacion), investigacion)

    elif modo == "--preparar":
        # Modo suscripción, paso 1: arma las instrucciones para Claude Code
        carpeta.mkdir(parents=True, exist_ok=True)
        pedido = carpeta / "pedido.md"
        pedido.write_text(pedido_claude_code(fecha, pilar, temas_recientes(fecha)), encoding="utf-8")
        print(pedido.relative_to(RAIZ))

    elif modo == "--validar":
        # Modo suscripción: Claude Code lo usa para revisar su post.json
        problemas = validar(json.loads((carpeta / "post.json").read_text(encoding="utf-8")))
        print("OK" if not problemas else "Corregir:\n- " + "\n- ".join(problemas))
        sys.exit(1 if problemas else 0)

    elif modo == "--terminar":
        # Modo suscripción, paso 2: con el post.json que escribió Claude Code, arma todo lo demás
        post = json.loads((carpeta / "post.json").read_text(encoding="utf-8"))
        problemas = validar(post)
        if problemas:
            raise SystemExit("El post no pasó la validación:\n- " + "\n- ".join(problemas))
        archivo_inv = carpeta / "investigacion.md"
        investigacion = archivo_inv.read_text(encoding="utf-8") if archivo_inv.exists() else ""
        (carpeta / "pedido.md").unlink(missing_ok=True)
        terminar(fecha, pilar, post, investigacion)

    else:
        raise SystemExit(f"Modo desconocido: {modo}")


if __name__ == "__main__":
    main()
