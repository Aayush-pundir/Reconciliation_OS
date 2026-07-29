import io

import pytest
from openpyxl import Workbook


@pytest.fixture
def make_xlsx():
    def _make(rows: list[list]) -> bytes:
        wb = Workbook()
        ws = wb.active
        for r in rows:
            ws.append(r)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    return _make
