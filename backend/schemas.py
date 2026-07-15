"""Pydantic schemas for CleanTec API."""
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, EmailStr, field_validator


CATEGORIE_PESO = ("BIANCHERIA_PIANA", "SPUGNA", "VARIE", "NON_CLASSIFICATO")


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "contabilita"
    cliente_id: Optional[str] = None
    can_edit_dates: Optional[bool] = False
    permissions: Optional[Dict[str, Dict[str, bool]]] = None


class ClienteIn(BaseModel):
    # Identificazione giuridica (obbligatoria)
    ragione_sociale: str
    partita_iva: str
    codice_fiscale: Optional[str] = ""
    indirizzo: str                       # sede legale (riga via + civico)
    cap: Optional[str] = ""
    comune: Optional[str] = ""
    provincia: Optional[str] = ""
    nazione: Optional[str] = "IT"
    email: EmailStr
    telefono: str
    pec: Optional[str] = ""
    codice_sdi: Optional[str] = ""       # codice destinatario SDI

    # Struttura operativa (denominazione + indirizzo di scarico)
    denominazione_struttura: Optional[str] = ""
    indirizzo_scarico: Optional[str] = ""

    tipologia: str = "hotel"
    listino_id: Optional[str] = None     # FK listini
    condizioni_pagamento: str = "30gg"
    giorni_ritiro: List[int] = Field(default_factory=list)
    note: Optional[str] = ""
    attivo: bool = True


class ArticoloIn(BaseModel):
    codice: str
    descrizione: str
    categoria: str = "biancheria"
    tipo: str = "capo"
    materiale: Optional[str] = ""
    lavaggio: str = "standard"
    temperatura: int = 60
    barcode: Optional[str] = ""
    peso_medio: float = 0.5
    categoria_peso: str = "NON_CLASSIFICATO"  # BIANCHERIA_PIANA | SPUGNA | VARIE | NON_CLASSIFICATO
    # Valore convenzionale singolo prodotto IVA esclusa
    prezzo: float = 0.0
    prezzo_tipo: str = "capo"
    # Nuovi driver FASE 2
    prezzo_noleggio: float = 0.0
    prezzo_lavaggio: float = 0.0
    giacenza: int = 0
    multiplo_quantita: int = 1  # 1 = unitario; 5/10/25 = ordini solo a multipli

    @field_validator("categoria_peso")
    @classmethod
    def _val_catpeso(cls, v):
        if v is None or v == "":
            return "NON_CLASSIFICATO"
        v = str(v).upper().strip()
        if v not in CATEGORIE_PESO:
            raise ValueError(f"categoria_peso deve essere una tra: {', '.join(CATEGORIE_PESO)}")
        return v


class MacchinaIn(BaseModel):
    codice: str
    tipo: str
    capacita_kg: float
    stato: str = "disponibile"
    reparto: str = "lavaggio"
    ore_lavoro: float = 0
    manutenzione_prossima: Optional[str] = None


class RitiroIn(BaseModel):
    cliente_id: str
    data_ritiro: str
    operatore: str
    peso_totale: float = 0
    quantita_totale: int = 0
    anomalie: Optional[str] = ""
    firma_url: Optional[str] = ""
    foto_urls: List[str] = Field(default_factory=list)
    note: Optional[str] = ""


class LottoIn(BaseModel):
    ritiro_id: str
    cliente_id: str
    articolo_id: str
    quantita: int = 1
    peso: float = 0
    priorita: str = "normale"


class CambiaStatoIn(BaseModel):
    nuovo_stato: str
    macchina_id: Optional[str] = None
    note: Optional[str] = ""
    esito: str = "ok"


class LavorazioneIn(BaseModel):
    lotto_id: str
    tipo: str
    macchina_id: Optional[str] = None
    programma: Optional[str] = ""
    temperatura: Optional[int] = 40
    detergenti: Optional[str] = ""
    tempo_min: Optional[int] = 60


class ConsegnaIn(BaseModel):
    cliente_id: str
    lotti_ids: List[str] = Field(default_factory=list)
    data_prevista: str
    autista: Optional[str] = ""
    note: Optional[str] = ""


class NonConformitaIn(BaseModel):
    lotto_id: Optional[str] = None
    tipo_difetto: str
    gravita: str = "media"
    foto_urls: List[str] = Field(default_factory=list)
    responsabile: Optional[str] = ""
    azione_correttiva: Optional[str] = ""


class FatturaIn(BaseModel):
    cliente_id: str
    data: str
    righe: List[Dict[str, Any]] = Field(default_factory=list)
    iva_pct: float = 22
    scadenza: Optional[str] = None


class MagazzinoIn(BaseModel):
    codice: str
    descrizione: str
    categoria: str = "detergente"   # detergente | dpi | consumabile | chimico | altro
    unita_misura: str = "pz"        # pz | kg | L | m | conf
    scorta_attuale: float = 0
    scorta_minima: float = 0
    prezzo_unitario: float = 0
    fornitore: Optional[str] = ""
    scadenza: Optional[str] = None
    note: Optional[str] = ""
    attivo: bool = True


class MovimentoIn(BaseModel):
    tipo: str                        # carico | scarico | rettifica
    quantita: float
    motivo: Optional[str] = ""       # scarico: lavaggio/pulizia/smaltito ; carico: acquisto/reso
    lotto_fornitore: Optional[str] = ""
    note: Optional[str] = ""


class TicketIn(BaseModel):
    macchina_id: str
    tipo: str = "guasto"           # guasto | programmata | preventiva | revisione
    priorita: str = "media"        # bassa | media | alta | critica
    titolo: str
    descrizione: str = ""
    assegnato_a: Optional[str] = ""
    fermo_macchina: bool = False


class InterventoIn(BaseModel):
    data_intervento: Optional[str] = None
    operatore: str
    descrizione: str
    durata_min: int = 0
    pezzi_usati: List[str] = Field(default_factory=list)
    costo: float = 0
    note: Optional[str] = ""


# ----------------------------------------------------------------------
# PATCH schemas — all fields optional, extras ignored.
# Use `.model_dump(exclude_unset=True)` in handlers to update only set fields.
# ----------------------------------------------------------------------
from pydantic import ConfigDict  # noqa: E402


class _PatchBase(BaseModel):
    model_config = ConfigDict(extra="ignore")


class PatchUserIn(_PatchBase):
    name: Optional[str] = None
    role: Optional[str] = None
    attivo: Optional[bool] = None
    cliente_id: Optional[str] = None
    password: Optional[str] = None
    can_edit_dates: Optional[bool] = None
    permissions: Optional[Dict[str, Dict[str, bool]]] = None


class PatchClienteIn(_PatchBase):
    ragione_sociale: Optional[str] = None
    partita_iva: Optional[str] = None
    codice_fiscale: Optional[str] = None
    indirizzo: Optional[str] = None
    cap: Optional[str] = None
    comune: Optional[str] = None
    provincia: Optional[str] = None
    nazione: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    pec: Optional[str] = None
    codice_sdi: Optional[str] = None
    denominazione_struttura: Optional[str] = None
    indirizzo_scarico: Optional[str] = None
    tipologia: Optional[str] = None
    listino_id: Optional[str] = None
    condizioni_pagamento: Optional[str] = None
    giorni_ritiro: Optional[List[int]] = None
    note: Optional[str] = None
    attivo: Optional[bool] = None


class PatchArticoloIn(_PatchBase):
    codice: Optional[str] = None
    descrizione: Optional[str] = None
    categoria: Optional[str] = None
    tipo: Optional[str] = None
    materiale: Optional[str] = None
    lavaggio: Optional[str] = None
    temperatura: Optional[int] = None
    barcode: Optional[str] = None
    peso_medio: Optional[float] = None
    categoria_peso: Optional[str] = None
    prezzo: Optional[float] = None
    prezzo_tipo: Optional[str] = None
    prezzo_noleggio: Optional[float] = None
    prezzo_lavaggio: Optional[float] = None
    giacenza: Optional[int] = None
    multiplo_quantita: Optional[int] = None

    @field_validator("categoria_peso")
    @classmethod
    def _val_catpeso_patch(cls, v):
        if v is None or v == "":
            return None
        v = str(v).upper().strip()
        if v not in CATEGORIE_PESO:
            raise ValueError(f"categoria_peso deve essere una tra: {', '.join(CATEGORIE_PESO)}")
        return v


class PatchMacchinaIn(_PatchBase):
    codice: Optional[str] = None
    tipo: Optional[str] = None
    capacita_kg: Optional[float] = None
    stato: Optional[str] = None
    reparto: Optional[str] = None
    ore_lavoro: Optional[float] = None
    manutenzione_prossima: Optional[str] = None


class PatchConsegnaIn(_PatchBase):
    stato: Optional[str] = None            # pianificata | in_consegna | consegnata | contestata
    autista: Optional[str] = None
    data_prevista: Optional[str] = None
    data_consegna_effettiva: Optional[str] = None
    lotti_ids: Optional[List[str]] = None
    firma_cliente_url: Optional[str] = None
    contestazioni: Optional[str] = None
    geolocation: Optional[Dict[str, Any]] = None
    note: Optional[str] = None


class PatchLavorazioneIn(_PatchBase):
    stato: Optional[str] = None            # pending | in_corso | completato
    macchina_id: Optional[str] = None
    programma: Optional[str] = None
    temperatura: Optional[int] = None
    detergenti: Optional[str] = None
    tempo_min: Optional[int] = None
    scarti: Optional[int] = None
    note: Optional[str] = None
    inizio: Optional[str] = None
    fine: Optional[str] = None


class PatchNonConformitaIn(_PatchBase):
    tipo_difetto: Optional[str] = None
    gravita: Optional[str] = None
    foto_urls: Optional[List[str]] = None
    responsabile: Optional[str] = None
    azione_correttiva: Optional[str] = None
    stato: Optional[str] = None            # aperta | in_lavorazione | risolta


class PatchFatturaIn(_PatchBase):
    stato: Optional[str] = None            # bozza | emessa | pagata | scaduta
    scadenza: Optional[str] = None
    data: Optional[str] = None
    righe: Optional[List[Dict[str, Any]]] = None
    iva_pct: Optional[float] = None


class PatchMagazzinoIn(_PatchBase):
    codice: Optional[str] = None
    descrizione: Optional[str] = None
    categoria: Optional[str] = None
    unita_misura: Optional[str] = None
    scorta_minima: Optional[float] = None
    prezzo_unitario: Optional[float] = None
    fornitore: Optional[str] = None
    scadenza: Optional[str] = None
    note: Optional[str] = None
    attivo: Optional[bool] = None


class PatchTicketIn(_PatchBase):
    stato: Optional[str] = None          # aperto | in_lavorazione | risolto | chiuso
    priorita: Optional[str] = None
    tipo: Optional[str] = None
    titolo: Optional[str] = None
    descrizione: Optional[str] = None
    assegnato_a: Optional[str] = None
    fermo_macchina: Optional[bool] = None
    soluzione: Optional[str] = None



# ============== FASE 2b — FORNITORI ==============

class FornitoreIn(BaseModel):
    # Identificazione giuridica
    ragione_sociale: str
    partita_iva: str
    codice_fiscale: Optional[str] = ""
    indirizzo: str
    email: EmailStr
    telefono: str
    pec: Optional[str] = ""
    codice_sdi: Optional[str] = ""
    iban: Optional[str] = ""
    sito: Optional[str] = ""

    # Categoria merceologica del fornitore
    categoria: str = "prodotti"  # prodotti | utenze | servizi | manutenzioni | trasporti | altro
    referente: Optional[str] = ""

    condizioni_pagamento: str = "30gg"
    note: Optional[str] = ""
    attivo: bool = True


class PatchFornitoreIn(_PatchBase):
    ragione_sociale: Optional[str] = None
    partita_iva: Optional[str] = None
    codice_fiscale: Optional[str] = None
    indirizzo: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    pec: Optional[str] = None
    codice_sdi: Optional[str] = None
    iban: Optional[str] = None
    sito: Optional[str] = None
    categoria: Optional[str] = None
    referente: Optional[str] = None
    condizioni_pagamento: Optional[str] = None
    note: Optional[str] = None
    attivo: Optional[bool] = None


class RigaDocFornIn(BaseModel):
    descrizione: str
    quantita: float = Field(gt=0)
    unita_misura: str = "pz"
    prezzo_unitario: float = Field(ge=0)


class DdtFornitoreIn(BaseModel):
    fornitore_id: str
    numero_fornitore: str           # numero DDT fornito dal fornitore stesso
    data: str                       # ISO yyyy-mm-dd
    righe: List[RigaDocFornIn]
    note: Optional[str] = ""


class PatchDdtFornitoreIn(_PatchBase):
    numero_fornitore: Optional[str] = None
    data: Optional[str] = None
    righe: Optional[List[RigaDocFornIn]] = None
    note: Optional[str] = None


class FatturaFornitoreIn(BaseModel):
    fornitore_id: str
    numero_fornitore: str           # numero fattura del fornitore
    data: str                       # ISO yyyy-mm-dd
    data_scadenza: Optional[str] = None
    ddt_fornitore_ids: List[str] = Field(default_factory=list)
    righe: List[RigaDocFornIn] = Field(default_factory=list)
    iva_perc: float = 22.0
    note: Optional[str] = ""


class PatchFatturaFornitoreIn(_PatchBase):
    numero_fornitore: Optional[str] = None
    data: Optional[str] = None
    data_scadenza: Optional[str] = None


# ============== FASE 4 — COSTI ==============

class CostoIn(BaseModel):
    categoria: str                        # personale | automezzi | utenze | prodotti
    data: str                             # yyyy-mm-dd (data registrazione/fattura)
    mese_riferimento: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")  # yyyy-mm (competenza)
    descrizione: str
    importo: float = Field(ge=0)

    # opzionali (context-aware per categoria)
    fornitore_id: Optional[str] = None
    fattura_fornitore_id: Optional[str] = None

    # Personale
    dipendente_nome: Optional[str] = None
    ore_lavorate: Optional[float] = None  # ore del mese
    tipo_rapporto: Optional[str] = None   # stipendio | contributi | tfr | trasferta | straordinario | altro

    # Automezzi
    automezzo_targa: Optional[str] = None
    automezzo_km: Optional[float] = None
    tipo_automezzo_costo: Optional[str] = None  # carburante | manutenzione | assicurazione | bollo | revisione | altro

    # Utenze
    tipo_utenza: Optional[str] = None     # gas | luce | acqua | telefono | internet | altro
    consumo: Optional[float] = None       # kWh, mc, unità
    unita_consumo: Optional[str] = None   # kWh, mc, min, ecc.

    # Prodotti consumabili
    articolo_codice: Optional[str] = None
    quantita: Optional[float] = None

    note: Optional[str] = ""


class PatchCostoIn(_PatchBase):
    categoria: Optional[str] = None
    data: Optional[str] = None
    mese_riferimento: Optional[str] = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    descrizione: Optional[str] = None
    importo: Optional[float] = None
    fornitore_id: Optional[str] = None
    fattura_fornitore_id: Optional[str] = None
    dipendente_nome: Optional[str] = None
    ore_lavorate: Optional[float] = None
    tipo_rapporto: Optional[str] = None
    automezzo_targa: Optional[str] = None
    automezzo_km: Optional[float] = None
    tipo_automezzo_costo: Optional[str] = None
    tipo_utenza: Optional[str] = None
    consumo: Optional[float] = None
    unita_consumo: Optional[str] = None
    articolo_codice: Optional[str] = None
    quantita: Optional[float] = None
    note: Optional[str] = None

    righe: Optional[List[RigaDocFornIn]] = None
    iva_perc: Optional[float] = None


# ============== FASE P3 — DIPENDENTI / AUTOMEZZI ==============

class DipendenteIn(BaseModel):
    nome: str
    codice_fiscale: Optional[str] = ""
    ruolo: Optional[str] = ""                 # es. "Operatore lavaggio", "Autista", ecc.
    email: Optional[str] = ""
    telefono: Optional[str] = ""
    data_assunzione: Optional[str] = None     # yyyy-mm-dd
    tipo_contratto: str = "indeterminato"     # indeterminato | determinato | apprendistato | collaborazione
    stipendio_mensile: float = Field(default=0, ge=0)   # lordo mensile
    ore_contrattuali: Optional[float] = 160
    note: Optional[str] = ""
    attivo: bool = True


class PatchDipendenteIn(_PatchBase):
    nome: Optional[str] = None
    codice_fiscale: Optional[str] = None
    ruolo: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    data_assunzione: Optional[str] = None
    tipo_contratto: Optional[str] = None
    stipendio_mensile: Optional[float] = None
    ore_contrattuali: Optional[float] = None
    note: Optional[str] = None
    attivo: Optional[bool] = None


class AutomezzoIn(BaseModel):
    targa: str
    marca_modello: Optional[str] = ""
    anno: Optional[int] = None
    alimentazione: Optional[str] = ""          # gasolio | benzina | elettrico | ibrido | altro
    km_attuali: float = Field(default=0, ge=0)
    note: Optional[str] = ""
    attivo: bool = True


class PatchAutomezzoIn(_PatchBase):
    targa: Optional[str] = None
    marca_modello: Optional[str] = None
    anno: Optional[int] = None
    alimentazione: Optional[str] = None
    km_attuali: Optional[float] = None
    note: Optional[str] = None
    attivo: Optional[bool] = None

    note: Optional[str] = None
    stato_pagamento: Optional[str] = None  # da_pagare | pagata
