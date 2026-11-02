# Bot @tino.invest

Todos los días a las 07:00 (hora de Paraguay) el bot:

1. Elige el tema según el pilar del día ([TEMAS.md](TEMAS.md)), sin repetir lo de las últimas 6 semanas.
2. Busca datos actuales en la web (Claude + búsqueda web), con fuentes.
3. Escribe el texto (máx. 500 caracteres, el límite de Threads) y el carrusel con tu estilo ([GUIA-DE-ESTILO.md](GUIA-DE-ESTILO.md)).
4. Arma los slides en PNG con la plantilla Swiss DRE ([plantilla/carrusel.html.j2](plantilla/carrusel.html.j2)).
5. Te abre un **issue en GitHub** con la vista previa y la lista de quién comentó INFO en la semana.
6. Cuando comentás `/publicar` en ese issue, lo publica en Threads.

Cuando confíes en lo que sale, activás el modo automático y publica solo (paso 7).

## Qué hay en cada carpeta

| Carpeta | Qué es |
|---|---|
| `bot/` | El código: `generar.py` (investiga y escribe), `render.py` (slides), `threads.py` + `publicar.py` (Threads), `informe_info.py` (quién comentó INFO) |
| `plantilla/` | El diseño de los slides |
| `posts/` | Un post por día: `post.json`, los PNG, la investigación y `publicado.json` cuando sale |
| `.github/workflows/` | Las tareas programadas de GitHub Actions |
| `ejemplos/` | Un post de prueba para ver la plantilla |

## Puesta en marcha (una sola vez)

### 1. Crear el repositorio en GitHub

Creá un repo **público** (por ejemplo `tino-invest-bot`) y subí estos archivos.
Tiene que ser público porque Threads descarga las imágenes desde una URL pública del repo.
Las claves no se ven: van guardadas como *secrets*.

### 2. Conectar Claude

Hay dos formas. El bot usa la que encuentre cargada (si están las dos, usa la suscripción).

**A. Con tu suscripción de Claude (sin costo extra)**

1. En la app Terminal de tu Mac, corré:
   ```bash
   npx -y @anthropic-ai/claude-code setup-token
   ```
2. Se abre el navegador: iniciá sesión con tu cuenta de Claude y autorizá.
3. La terminal muestra un token largo (`sk-ant-oat…`). Copialo.
4. En GitHub: **Settings → Secrets and variables → Actions → New repository secret**.
   Nombre `CLAUDE_CODE_OAUTH_TOKEN`, valor: el token.

Cada post consume parte del límite de uso de tu suscripción, como si le pidieras el post a Claude a mano.

**B. Con la API (pago por uso)**

1. Entrá a [console.anthropic.com](https://console.anthropic.com), cargá saldo y creá una API key.
2. Guardala como secret `ANTHROPIC_API_KEY`.

Costo estimado: entre USD 0,30 y 0,60 por post (modelo Claude Opus 5.5 + hasta 8 búsquedas web), o sea, unos USD 10 a 18 por mes.

### 3. Acceso a Threads (cuenta de developer de Meta)

1. Entrá a [developers.facebook.com](https://developers.facebook.com) con tu cuenta y creá una app con el caso de uso **"Acceder a la API de Threads"**.
2. En la app, agregá permisos: `threads_basic`, `threads_content_publish` y `threads_read_replies`.
3. En **Roles → Testers de Threads**, agregá tu cuenta @tino.invest y aceptá la invitación desde Threads
   (Configuración → Cuenta → Permisos de sitios web).
4. Generá un **token de larga duración** (dura 60 días) para tu usuario desde el panel de la app.
5. Guardalo en GitHub como secret `THREADS_ACCESS_TOKEN`.

Mientras la app esté en modo desarrollo y vos seas tester, no hace falta que Meta la revise: solo publica en tu propia cuenta.

### 4. Renovación automática del token

El token de Threads vence a los 60 días. Un workflow lo renueva todos los lunes, pero para guardarlo necesita permiso:

1. En GitHub: **Settings (de tu perfil) → Developer settings → Fine-grained tokens → Generate new token**.
2. Elegí solo este repositorio y dale permiso **Secrets: Read and write**.
3. Guardalo como secret `GH_PAT` en el repo.

### 5. Primera prueba

**Actions → Generar post del día → Run workflow**. En unos minutos aparece un issue "Borrador AAAA-MM-DD" con el texto y los slides.

### 6. Aprobar o descartar

- **Publicar:** comentá `/publicar` en el issue. Solo funciona si lo comentás vos (el dueño del repo).
- **Cambiar algo:** editá `posts/AAAA-MM-DD/post.json` en GitHub y después comentá `/publicar`; los slides se rearman con tus cambios.
- **Descartar:** cerrá el issue.

### 7. Modo automático (cuando quieras)

**Settings → Secrets and variables → Actions → Variables → New variable**: `PUBLICAR_AUTOMATICO` = `true`.
Desde ahí publica solo a las 07:00. Para volver a aprobar a mano, borrá la variable.

## Probar los slides en tu compu

```bash
pip install -r requirements.txt
python -m playwright install chromium
python bot/render.py ejemplos/post-ejemplo.json
```

## Pendiente

- Fotos de stock (Pexels) para la portada.
- Lista fija de fuentes de datos preferidas.
