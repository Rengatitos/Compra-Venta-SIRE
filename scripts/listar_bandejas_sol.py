"""Enumera las opciones del combo «Tipo de consulta» del portal SOL.

El scraper elige la bandeja por nombre (`scraping_sunat.BANDEJAS`) a partir de
una lista transcrita a mano de nueve opciones. El combo es un
`dijit.FilteringSelect` paginado («Más opciones»), así que nunca se leyó
completo; este script entra con las credenciales de una empresa, abre la
consulta de comprobantes y vuelca todas las opciones, primero desde el store
del widget y, si no está accesible, recorriendo la lista desplegable.

    uv run python scripts/listar_bandejas_sol.py --ruc 20610202251
    uv run python scripts/listar_bandejas_sol.py --ruc 20610202251 --headed

Escribe el resultado en `logs/bandejas_sol.txt`. No toca la base de datos.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.encryption import decrypt_password  # noqa: E402
from app.services import scraping_sunat as sc  # noqa: E402

SALIDA = Path(__file__).resolve().parents[1] / "logs" / "bandejas_sol.txt"

# Lee el store del FilteringSelect sin abrir la lista: es la fuente completa,
# sin paginar. Devuelve `null` si el widget o el store no están donde se espera.
_JS_OPCIONES_STORE = """() => {
    const dj = window.dijit || (window.require && window.require('dijit/registry'));
    if (!dj || !dj.byId) return null;
    const w = dj.byId('criterio.tipoConsulta');
    if (!w) return null;
    const attr = w.searchAttr || 'name';
    const st = w.store;
    if (!st) return null;
    if (Array.isArray(st.data)) return st.data.map(d => String(d[attr]));
    if (Array.isArray(st._arrayOfAllItems) && st._arrayOfAllItems.length) {
        return st._arrayOfAllItems.map(i => String(st.getValue(i, attr)));
    }
    if (typeof st.fetch === 'function') {
        // dojo.data.ItemFileReadStore: la lectura es asíncrona aunque los
        // datos ya estén en memoria.
        return new Promise(resolve => st.fetch({
            query: {}, queryOptions: {deep: true},
            onComplete: items => resolve(items.map(i => String(st.getValue(i, attr)))),
            onError: () => resolve(null),
        }));
    }
    if (typeof st.query === 'function') {
        const r = st.query({});
        if (Array.isArray(r)) return r.map(d => String(d[attr]));
    }
    return null;
}"""

# Texto de cada opción visible en la lista desplegada del combo, y si el botón
# «Más opciones» sigue activo para seguir paginando. Los botones de paginación
# también son `li.dijitMenuItem`, así que se excluyen por clase.
_JS_OPCIONES_VISIBLES = """() => {
    const popup = document.getElementById('criterio.tipoConsulta_popup');
    if (!popup) return {items: [], haySiguiente: false, sinPopup: true};
    const items = Array.from(popup.querySelectorAll('li.dijitMenuItem'))
        .filter(li => li.offsetParent !== null)
        .filter(li => !li.classList.contains('dijitMenuPreviousButton')
                   && !li.classList.contains('dijitMenuNextButton'))
        .map(li => li.textContent.trim())
        .filter(Boolean);
    const siguiente = popup.querySelector('li.dijitMenuNextButton');
    const haySiguiente = !!siguiente && siguiente.offsetParent !== null
        && !siguiente.classList.contains('dijitMenuItemDisabled');
    return {items, haySiguiente, sinPopup: false};
}"""


def _empresa(ruc: str) -> dict:
    load_dotenv()
    cliente = MongoClient(os.environ["MONGO_URI"], serverSelectionTimeoutMS=5000)
    empresa = cliente[os.environ.get("MONGO_FACTURASDB_NAME", "Mod_Facturas")].empresas.find_one(
        {"ruc": ruc}
    )
    if not empresa:
        sys.exit(f"No hay empresa con RUC {ruc} en la base local")
    return empresa


def _por_paginacion(iframe, log) -> list[str]:
    combo = iframe.locator(sc.SEL_TIPO_CONSULTA).first
    combo.click()
    combo.fill("")
    # La flecha del widget abre la lista completa (sin filtro); si no se
    # encuentra, la flecha abajo del teclado hace lo mismo.
    flecha = combo.locator(
        "xpath=ancestor::*[contains(@class,'dijitComboBox')][1]"
        "//*[contains(@class,'dijitArrowButton')]"
    ).first
    if flecha.count() > 0:
        flecha.click()
    else:
        combo.press("ArrowDown")
    popup = iframe.locator("#criterio\\.tipoConsulta_popup")
    popup.wait_for(state="visible", timeout=5000)
    opciones: list[str] = []
    for _ in range(20):
        iframe.locator("body").wait_for(state="attached", timeout=5000)
        pagina = iframe.locator("body").evaluate(_JS_OPCIONES_VISIBLES)
        nuevas = [o for o in pagina["items"] if o not in opciones]
        opciones.extend(nuevas)
        log(f"página con {len(pagina['items'])} opciones, {len(nuevas)} nuevas")
        if not pagina["haySiguiente"] or not nuevas:
            break
        popup.locator("li.dijitMenuNextButton").first.click()
    return opciones


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ruc", required=True)
    parser.add_argument("--headed", action="store_true", help="abre el navegador visible")
    args = parser.parse_args()

    empresa = _empresa(args.ruc)
    clave = decrypt_password(empresa["password"])

    def log(msg: str) -> None:
        print(msg, flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        try:
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            )
            page = context.new_page()
            sc._login_con_reintentos(page, empresa["ruc"], empresa["usuario"], clave, log)
            sc._abrir_modulo_empresas(page, log)
            iframe = page.frame_locator("#iframeApplication")
            sc._abrir_consulta(page, iframe, 15000)

            opciones = iframe.locator("body").evaluate(_JS_OPCIONES_STORE)
            fuente = "store del widget"
            if not opciones:
                fuente = "lista desplegable paginada"
                opciones = _por_paginacion(iframe, log)
        finally:
            browser.close()

    conocidas = {
        nombre
        for por_tipo in sc.BANDEJAS.values()
        for nombre in por_tipo.values()
    } | set(sc.BANDEJAS_SOBRE_BOLETA.values())
    lineas = [f"# Opciones del combo «Tipo de consulta» ({fuente}) — RUC {args.ruc}", ""]
    for opcion in opciones:
        marca = "conocida" if opcion in conocidas else "NUEVA"
        lineas.append(f"{opcion}\t{marca}")
    lineas += ["", f"Total: {len(opciones)}; sin usar por el scraper: "
               f"{sum(1 for o in opciones if o not in conocidas)}"]
    SALIDA.parent.mkdir(exist_ok=True)
    SALIDA.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("\n".join(lineas))
    print(f"\nGuardado en {SALIDA}")


if __name__ == "__main__":
    main()
