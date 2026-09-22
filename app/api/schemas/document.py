from typing import Optional

from pydantic import BaseModel


class DocumentExtractResponse(BaseModel):
    text: str
    has_complex_layout: bool = False


class ProductInfoFormatRequest(BaseModel):
    text: str
    product_name: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None


class ProductInfoFormatResponse(BaseModel):
    html: str
