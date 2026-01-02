import frappe
from frappe.utils import flt

KG_UOM_CANDIDATES = (
	"Kilogram",
	"Kg",
	"KG",
	"Kgs",
	"Kilograms",
)

_TON_UOMS = {
	"ton",
	"tons",
	"tonne",
	"tonnes",
	"mt",
	"metric ton",
	"metric tonne",
}

_KG_UOMS = {
	"kg",
	"kilogram",
	"kilograms",
	"kgs",
}


def normalize_uom(value: str | None) -> str:
	return (value or "").strip().lower()


def is_ton_uom(value: str | None) -> bool:
	return normalize_uom(value) in _TON_UOMS


def is_kg_uom(value: str | None) -> bool:
	return normalize_uom(value) in _KG_UOMS


def resolve_kg_uom() -> str | None:
	for candidate in KG_UOM_CANDIDATES:
		if frappe.db.exists("Unit of Measurement", candidate):
			return candidate
	return None


def conversion_factor(from_uom: str | None, to_uom: str | None) -> float:
	if not from_uom or not to_uom:
		return 1.0
	if is_ton_uom(from_uom) and is_kg_uom(to_uom):
		return 1000.0
	if is_kg_uom(from_uom) and is_ton_uom(to_uom):
		return 0.001
	return 1.0


def convert_quantity(quantity: float | None, from_uom: str | None, to_uom: str | None) -> float:
	return flt(quantity or 0) * conversion_factor(from_uom, to_uom)


def convert_rate(rate: float | None, from_uom: str | None, to_uom: str | None) -> float:
	factor = conversion_factor(from_uom, to_uom)
	if not factor:
		return flt(rate or 0)
	return flt(rate or 0) / factor
