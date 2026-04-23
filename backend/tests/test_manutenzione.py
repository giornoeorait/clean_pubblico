"""Tests for Manutenzione module (tickets + interventi)."""
import os
import re
import pytest
import requests
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://wash-ops-central.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "admin": ("admin@cleantec.it", "admin123"),
    "produzione": ("produzione@cleantec.it", "produzione123"),
    "logistica": ("logistica@cleantec.it", "logistica123"),
    "qualita": ("qualita@cleantec.it", "qualita123"),
    "contabilita": ("contabilita@cleantec.it", "contabilita123"),
    "cliente": ("cliente@cleantec.it", "cliente123"),
}


@pytest.fixture(scope="module")
def tokens():
    out = {}
    for role, (email, pwd) in CREDS.items():
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=20)
        assert r.status_code == 200, f"login {role} failed"
        out[role] = r.json()["token"]
    return out


def H(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _mongo():
    from pymongo import MongoClient
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    name = os.environ.get("DB_NAME", "test_database")
    return MongoClient(url)[name]


# ---------- Seeded tickets ----------
def test_seeded_tickets_list_and_shape(tokens):
    r = requests.get(f"{API}/tickets", headers=H(tokens["admin"]))
    assert r.status_code == 200
    tickets = r.json()
    assert isinstance(tickets, list)
    assert len(tickets) >= 4
    # no _id leak
    for t in tickets:
        assert "_id" not in t
        assert "id" in t
        assert "numero" in t and re.match(r"TKT-\d{4}-\d{5}", t["numero"])
        assert t["tipo"] in ("guasto", "programmata", "preventiva", "revisione")
        assert t["priorita"] in ("bassa", "media", "alta", "critica")
        assert t["stato"] in ("aperto", "in_lavorazione", "risolto", "chiuso")
        assert "macchina_codice" in t
    # check presence of the 4 seeded numeros
    numeros = {t["numero"] for t in tickets}
    for n in ("TKT-2026-00001", "TKT-2026-00002", "TKT-2026-00003", "TKT-2026-00004"):
        assert n in numeros, f"missing seeded {n}"


def test_filter_by_stato(tokens):
    r = requests.get(f"{API}/tickets?stato=aperto", headers=H(tokens["admin"]))
    assert r.status_code == 200
    for t in r.json():
        assert t["stato"] == "aperto"


def test_filter_by_priorita(tokens):
    r = requests.get(f"{API}/tickets?priorita=critica", headers=H(tokens["admin"]))
    assert r.status_code == 200
    for t in r.json():
        assert t["priorita"] == "critica"


def test_filter_by_macchina_id(tokens):
    macchine = requests.get(f"{API}/macchine", headers=H(tokens["admin"])).json()
    mid = macchine[0]["id"]
    r = requests.get(f"{API}/tickets?macchina_id={mid}", headers=H(tokens["admin"]))
    assert r.status_code == 200
    for t in r.json():
        assert t["macchina_id"] == mid


# ---------- Create ticket ----------
def _pick_macchina_disponibile(tokens):
    macchine = requests.get(f"{API}/macchine", headers=H(tokens["admin"])).json()
    # prefer one with no guasto to avoid interactions
    for m in macchine:
        if m["stato"] not in ("guasto", "manutenzione"):
            return m
    return macchine[0]


def test_create_ticket_auto_numero_and_fields(tokens):
    m = _pick_macchina_disponibile(tokens)
    body = {
        "macchina_id": m["id"],
        "tipo": "guasto",
        "priorita": "media",
        "titolo": "TEST_create_basic",
        "descrizione": "Test ticket creation",
        "fermo_macchina": False,
    }
    r = requests.post(f"{API}/tickets", headers=H(tokens["produzione"]), json=body)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert re.match(r"TKT-\d{4}-\d{5}", doc["numero"])
    assert doc["macchina_codice"] == m["codice"]
    assert doc["stato"] == "aperto"
    assert doc["segnalato_da"]  # user name
    assert doc["interventi_count"] == 0
    assert doc["durata_totale_min"] == 0
    assert doc["costo_totale"] == 0.0
    # persisted via GET
    g = requests.get(f"{API}/tickets/{doc['id']}", headers=H(tokens["admin"]))
    assert g.status_code == 200
    assert g.json()["numero"] == doc["numero"]


def test_create_ticket_fermo_macchina_sets_guasto_and_resolve_restores(tokens):
    # pick a currently disponibile macchina and ensure stato toggles
    macchine = requests.get(f"{API}/macchine", headers=H(tokens["admin"])).json()
    target = next((m for m in macchine if m["stato"] == "disponibile"), None)
    assert target, "need at least 1 macchina disponibile"
    mid = target["id"]
    body = {"macchina_id": mid, "tipo": "guasto", "priorita": "alta",
            "titolo": "TEST_fermo", "fermo_macchina": True}
    r = requests.post(f"{API}/tickets", headers=H(tokens["produzione"]), json=body)
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    # verify macchina stato changed to guasto
    mlist = requests.get(f"{API}/macchine", headers=H(tokens["admin"])).json()
    m_after = [x for x in mlist if x["id"] == mid][0]
    assert m_after["stato"] == "guasto", f"expected guasto got {m_after['stato']}"

    # Resolve ticket -> macchina should restore to disponibile
    p = requests.patch(f"{API}/tickets/{tid}", headers=H(tokens["produzione"]),
                       json={"stato": "risolto"})
    assert p.status_code == 200
    mlist2 = requests.get(f"{API}/macchine", headers=H(tokens["admin"])).json()
    m_final = [x for x in mlist2 if x["id"] == mid][0]
    assert m_final["stato"] == "disponibile", f"expected disponibile got {m_final['stato']}"

    # chiuso_at must be set
    g = requests.get(f"{API}/tickets/{tid}", headers=H(tokens["admin"])).json()
    assert g.get("chiuso_at"), f"chiuso_at missing on resolved ticket: {g}"


def test_create_ticket_non_existing_macchina_404(tokens):
    r = requests.post(f"{API}/tickets", headers=H(tokens["produzione"]), json={
        "macchina_id": "non-existing-id-xxx", "titolo": "TEST_404",
    })
    assert r.status_code == 404


def test_get_ticket_with_embedded_interventi_sorted_desc(tokens):
    # use seeded TKT-2026-00002 which has 2 interventi
    tickets = requests.get(f"{API}/tickets", headers=H(tokens["admin"])).json()
    t = next((x for x in tickets if x["numero"] == "TKT-2026-00002"), None)
    assert t, "seeded TKT-2026-00002 missing"
    r = requests.get(f"{API}/tickets/{t['id']}", headers=H(tokens["admin"]))
    assert r.status_code == 200
    doc = r.json()
    assert "interventi" in doc
    assert len(doc["interventi"]) == 2
    # sorted desc by data_intervento
    dates = [i["data_intervento"] for i in doc["interventi"]]
    assert dates == sorted(dates, reverse=True), f"interventi not sorted desc: {dates}"


# ---------- Interventi ----------
def test_post_intervento_recomputes_totals_and_auto_transition(tokens):
    m = _pick_macchina_disponibile(tokens)
    # create open ticket
    r = requests.post(f"{API}/tickets", headers=H(tokens["produzione"]), json={
        "macchina_id": m["id"], "titolo": "TEST_interv", "priorita": "media",
    })
    assert r.status_code == 200
    tid = r.json()["id"]
    assert r.json()["stato"] == "aperto"

    # add intervento with durata + costo and date string
    body = {
        "data_intervento": "2026-01-15",
        "operatore": "Mario Test",
        "descrizione": "Diagnosi",
        "durata_min": 60,
        "costo": 100.0,
    }
    p = requests.post(f"{API}/tickets/{tid}/interventi", headers=H(tokens["produzione"]), json=body)
    assert p.status_code == 200, p.text
    iv = p.json()
    assert iv["ticket_id"] == tid
    assert iv["operatore"] == "Mario Test"

    # ticket should be auto-transitioned + recomputed
    g = requests.get(f"{API}/tickets/{tid}", headers=H(tokens["admin"])).json()
    assert g["stato"] == "in_lavorazione"
    assert g["interventi_count"] == 1
    assert g["durata_totale_min"] == 60
    assert g["costo_totale"] == 100.0

    # add 2nd intervento
    p2 = requests.post(f"{API}/tickets/{tid}/interventi", headers=H(tokens["produzione"]), json={
        "data_intervento": "2026-01-16", "operatore": "Luca", "descrizione": "fix",
        "durata_min": 30, "costo": 50.5,
    })
    assert p2.status_code == 200
    g2 = requests.get(f"{API}/tickets/{tid}", headers=H(tokens["admin"])).json()
    assert g2["interventi_count"] == 2
    assert g2["durata_totale_min"] == 90
    assert g2["costo_totale"] == 150.5

    # verify DB: data_intervento stored as BSON datetime
    db = _mongo()
    for iv_doc in db.interventi.find({"ticket_id": tid}):
        assert isinstance(iv_doc["data_intervento"], datetime), \
            f"data_intervento not datetime: {type(iv_doc['data_intervento'])}"

    # list interventi sorted desc
    lst = requests.get(f"{API}/tickets/{tid}/interventi", headers=H(tokens["admin"])).json()
    assert len(lst) == 2
    dates = [i["data_intervento"] for i in lst]
    assert dates == sorted(dates, reverse=True)


def test_patch_ticket_stato_chiuso_sets_chiuso_at(tokens):
    m = _pick_macchina_disponibile(tokens)
    r = requests.post(f"{API}/tickets", headers=H(tokens["produzione"]), json={
        "macchina_id": m["id"], "titolo": "TEST_close", "priorita": "bassa",
    })
    tid = r.json()["id"]
    p = requests.patch(f"{API}/tickets/{tid}", headers=H(tokens["produzione"]),
                       json={"stato": "chiuso"})
    assert p.status_code == 200
    g = requests.get(f"{API}/tickets/{tid}", headers=H(tokens["admin"])).json()
    assert g["stato"] == "chiuso"
    assert g.get("chiuso_at")


def test_delete_ticket_admin_only_and_cascade_interventi(tokens):
    m = _pick_macchina_disponibile(tokens)
    r = requests.post(f"{API}/tickets", headers=H(tokens["admin"]), json={
        "macchina_id": m["id"], "titolo": "TEST_delete",
    })
    tid = r.json()["id"]
    # add intervento
    requests.post(f"{API}/tickets/{tid}/interventi", headers=H(tokens["admin"]),
                  json={"operatore": "X", "descrizione": "y", "durata_min": 10, "costo": 5})

    # produzione cannot delete (admin-only)
    d_bad = requests.delete(f"{API}/tickets/{tid}", headers=H(tokens["produzione"]))
    assert d_bad.status_code == 403

    # admin delete
    d = requests.delete(f"{API}/tickets/{tid}", headers=H(tokens["admin"]))
    assert d.status_code == 200

    # ticket gone
    g = requests.get(f"{API}/tickets/{tid}", headers=H(tokens["admin"]))
    assert g.status_code == 404
    # interventi also deleted
    db = _mongo()
    assert db.interventi.count_documents({"ticket_id": tid}) == 0


# ---------- Storico manutenzione ----------
def test_storico_manutenzione_for_macchina(tokens):
    # use seeded LAV-01 which has TKT-2026-00002 (chiuso, costo 180)
    macchine = requests.get(f"{API}/macchine", headers=H(tokens["admin"])).json()
    lav01 = next((m for m in macchine if m["codice"] == "LAV-01"), None)
    assert lav01, "LAV-01 missing"
    r = requests.get(f"{API}/macchine/{lav01['id']}/storico-manutenzione", headers=H(tokens["admin"]))
    assert r.status_code == 200
    s = r.json()
    for key in ("totale", "aperti", "risolti", "costo_totale", "durata_totale_min", "tickets"):
        assert key in s, f"missing {key}"
    assert s["totale"] >= 1
    assert s["risolti"] >= 1  # TKT-2026-00002 is chiuso
    assert s["costo_totale"] >= 180.0
    for t in s["tickets"]:
        assert t["macchina_id"] == lav01["id"]


# ---------- RBAC ----------
@pytest.mark.parametrize("role", ["qualita", "logistica", "contabilita", "cliente"])
def test_rbac_non_write_roles_cannot_post_ticket(tokens, role):
    macchine = requests.get(f"{API}/macchine", headers=H(tokens["admin"])).json()
    r = requests.post(f"{API}/tickets", headers=H(tokens[role]), json={
        "macchina_id": macchine[0]["id"], "titolo": "TEST_rbac",
    })
    assert r.status_code == 403, f"role={role} got {r.status_code}"


@pytest.mark.parametrize("role", ["qualita", "logistica", "contabilita", "cliente"])
def test_rbac_non_write_roles_cannot_post_intervento(tokens, role):
    # pick any seeded ticket
    tickets = requests.get(f"{API}/tickets", headers=H(tokens["admin"])).json()
    tid = tickets[0]["id"]
    r = requests.post(f"{API}/tickets/{tid}/interventi", headers=H(tokens[role]), json={
        "operatore": "X", "descrizione": "y", "durata_min": 10, "costo": 1,
    })
    assert r.status_code == 403


def test_admin_always_allowed_to_post_ticket(tokens):
    macchine = requests.get(f"{API}/macchine", headers=H(tokens["admin"])).json()
    r = requests.post(f"{API}/tickets", headers=H(tokens["admin"]), json={
        "macchina_id": macchine[0]["id"], "titolo": "TEST_admin_allowed",
    })
    assert r.status_code == 200


# ---------- Counters + KPI ----------
def test_counter_ticket_exists_and_synced():
    db = _mongo()
    counter = db.counters.find_one({"_id": "ticket"})
    assert counter is not None, "ticket counter missing"
    count = db.tickets.count_documents({})
    # counter.seq must be >= tickets count (since new inserts increment)
    assert counter["seq"] >= count, f"counter.seq={counter['seq']} < count={count}"


def test_dashboard_kpi_tickets_aperti(tokens):
    r = requests.get(f"{API}/dashboard/kpi", headers=H(tokens["admin"]))
    assert r.status_code == 200
    j = r.json()
    assert "tickets_aperti" in j
    assert isinstance(j["tickets_aperti"], int)
    # verify matches count of tickets in aperto + in_lavorazione
    all_tickets = requests.get(f"{API}/tickets", headers=H(tokens["admin"])).json()
    expected = sum(1 for t in all_tickets if t["stato"] in ("aperto", "in_lavorazione"))
    assert j["tickets_aperti"] == expected, \
        f"kpi={j['tickets_aperti']} expected={expected}"


def test_ticket_indexes_exist():
    db = _mongo()
    idxs = db.tickets.index_information()
    fields = set()
    for _, info in idxs.items():
        for k, _d in info.get("key", []):
            fields.add(k)
    for needed in ("id", "macchina_id", "stato", "created_at"):
        assert needed in fields, f"missing tickets index on {needed}"
    iidx = db.interventi.index_information()
    ifields = set()
    for _, info in iidx.items():
        for k, _d in info.get("key", []):
            ifields.add(k)
    assert "ticket_id" in ifields
