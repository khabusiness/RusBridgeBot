from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlencode

from app.config import Settings


@dataclass(slots=True)
class PaymentLink:
    pay_url: str
    success_url: str
    fail_url: str
    inv_id: int
    out_sum: str
    provider_mode: str


class RobokassaService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.hash_algo = settings.robokassa_hash_algo.lower()
        if self.hash_algo not in {"md5", "sha1", "sha256", "sha512"}:
            raise ValueError(f"Unsupported hash algorithm: {self.hash_algo}")

    def _digest(self, payload: str) -> str:
        encoded = payload.encode("utf-8")
        if self.hash_algo == "md5":
            return hashlib.md5(encoded).hexdigest()  # noqa: S324 - provider-compatible choice
        if self.hash_algo == "sha1":
            return hashlib.sha1(encoded).hexdigest()  # noqa: S324 - provider-compatible choice
        if self.hash_algo == "sha256":
            return hashlib.sha256(encoded).hexdigest()
        return hashlib.sha512(encoded).hexdigest()

    def _append_shp_part(self, parts: list[str], shp_fields: Mapping[str, str]) -> None:
        for key in sorted(shp_fields.keys(), key=str.lower):
            parts.append(f"{key}={shp_fields[key]}")

    def _signature_base(self, *, out_sum: str, inv_id: str, password: str, shp_fields: Mapping[str, str]) -> str:
        parts = [out_sum, inv_id, password]
        self._append_shp_part(parts, shp_fields)
        return ":".join(parts)

    def create_payment_link(
        self,
        *,
        order_id: str,
        inv_id: int,
        amount_rub: int,
        description: str,
    ) -> PaymentLink:
        out_sum = f"{amount_rub:.2f}"
        if self.settings.payment_test_mode:
            return PaymentLink(
                pay_url=self.settings.mock_payment_success_url,
                success_url=self.settings.mock_payment_success_url,
                fail_url=self.settings.mock_payment_fail_url,
                inv_id=inv_id,
                out_sum=out_sum,
                provider_mode="stub",
            )

        shp_fields = {"Shp_order_id": order_id}
        base = ":".join(
            [
                self.settings.robokassa_merchant_login,
                out_sum,
                str(inv_id),
                self.settings.robokassa_password1,
                *[f"{key}={shp_fields[key]}" for key in sorted(shp_fields.keys(), key=str.lower)],
            ]
        )
        signature = self._digest(base)
        query = {
            "MerchantLogin": self.settings.robokassa_merchant_login,
            "OutSum": out_sum,
            "InvId": str(inv_id),
            "Description": description,
            "SignatureValue": signature,
            "Culture": "ru",
            "Shp_order_id": order_id,
        }
        if self.settings.robokassa_is_test:
            query["IsTest"] = "1"

        pay_url = "https://auth.robokassa.ru/Merchant/Index.aspx?" + urlencode(query)
        return PaymentLink(
            pay_url=pay_url,
            success_url=self.settings.robokassa_success_url,
            fail_url=self.settings.robokassa_fail_url,
            inv_id=inv_id,
            out_sum=out_sum,
            provider_mode="robokassa",
        )

    def verify_result_signature(self, params: Mapping[str, str]) -> bool:
        out_sum = params.get("OutSum", "").strip()
        inv_id = params.get("InvId", "").strip()
        provided = params.get("SignatureValue", "").strip().lower()
        shp_fields = {k: v for k, v in params.items() if k.startswith("Shp_")}

        base = self._signature_base(
            out_sum=out_sum,
            inv_id=inv_id,
            password=self.settings.robokassa_password2,
            shp_fields=shp_fields,
        )
        expected = self._digest(base).lower()
        return expected == provided
