"""Pydantic schemas for CleanTec API."""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, EmailStr


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "produzione"
    cliente_id: Optional[str] = None


class ClienteIn(BaseModel):
    ragione_sociale: str
    partita_iva: Optional[str] = ""
    codice_fiscale: Optional[str] = ""
    indirizzo: Optional[str] = ""
    email: Optional[str] = ""
    telefono: Optional[str] = ""
    tipologia: str = "hotel"
    listino: str = "standard"
    condizioni_pagamento: str = "30gg"
    giorni_ritiro: List[int] = Field(default_factory=list)
    sla_ore: int = 48
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
    prezzo: float = 0.0
    prezzo_tipo: str = "capo"


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
