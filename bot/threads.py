"""Cliente mínimo de la API de Threads (Meta): publicar carruseles y leer respuestas."""
import os
import time

import requests

API = "https://graph.threads.net/v1.0"


class Threads:
    def __init__(self, token=None):
        self.token = token or os.environ["THREADS_ACCESS_TOKEN"]
        self._usuario = None

    def _get(self, ruta, **params):
        r = requests.get(f"{API}/{ruta}", params={**params, "access_token": self.token}, timeout=60)
        r.raise_for_status()
        return r.json()

    def _post(self, ruta, **params):
        r = requests.post(f"{API}/{ruta}", params={**params, "access_token": self.token}, timeout=60)
        if not r.ok:
            raise RuntimeError(f"Threads respondió {r.status_code}: {r.text}")
        return r.json()

    @property
    def usuario(self):
        if self._usuario is None:
            self._usuario = self._get("me", fields="id,username")
        return self._usuario

    def _esperar_contenedor(self, contenedor_id, intentos=20):
        """Threads procesa cada imagen antes de publicarla; esperamos a que quede FINISHED."""
        for _ in range(intentos):
            estado = self._get(contenedor_id, fields="status,error_message")
            if estado.get("status") == "FINISHED":
                return
            if estado.get("status") in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"El contenedor {contenedor_id} falló: {estado}")
            time.sleep(10)
        raise RuntimeError(f"El contenedor {contenedor_id} no terminó de procesarse a tiempo")

    def publicar_carrusel(self, texto, urls_imagenes):
        """Publica un carrusel (2 a 20 imágenes) con texto. Devuelve {id, permalink}."""
        uid = self.usuario["id"]
        hijos = []
        for url in urls_imagenes:
            item = self._post(f"{uid}/threads", media_type="IMAGE", image_url=url, is_carousel_item="true")
            hijos.append(item["id"])
        for hijo in hijos:
            self._esperar_contenedor(hijo)

        carrusel = self._post(f"{uid}/threads", media_type="CAROUSEL", children=",".join(hijos), text=texto)
        self._esperar_contenedor(carrusel["id"])
        publicado = self._post(f"{uid}/threads_publish", creation_id=carrusel["id"])
        datos = self._get(publicado["id"], fields="id,permalink")
        return {"id": datos["id"], "permalink": datos.get("permalink", "")}

    def posts_desde(self, desde_unix):
        datos = self._get("me/threads", fields="id,timestamp,permalink,text", since=desde_unix, limit=50)
        return datos.get("data", [])

    def respuestas(self, post_id):
        datos = self._get(f"{post_id}/replies", fields="id,text,username,timestamp,permalink")
        return datos.get("data", [])
