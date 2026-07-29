from app.recon.base import RunContext, UploadedFile
from app.recon.registry import get_module
from app.recon.modules.bank_addmoney import extract_bank_utr, extract_ops_utr


def test_trxv_prefix_excludes_row():
    assert extract_ops_utr("TRXV000111") is None


def test_re1_prefix_strips_first_three_chars():
    assert extract_ops_utr("RE1998877") == "998877"


def test_default_extracts_digits_only():
    assert extract_ops_utr("AB-123-45") == "12345"


def test_bank_imps_prefix_takes_first_12_digits():
    assert extract_bank_utr("IMPS/123456789012/XYZ/ACME") == "123456789012"


def test_bank_ift_prefix_takes_first_11_digits():
    assert extract_bank_utr("IFT/12345678901/ABC") == "12345678901"


def test_bank_ineft_extracts_between_eroute_markers():
    assert extract_bank_utr("~EROUTE~333999~ INEFT desc") == "333999"


def test_bank_neft_extracts_between_first_two_slashes():
    assert extract_bank_utr("NEFT/998877/SOMEBANK/REF") == "998877"


def _run(make_xlsx):
    ops_rows = [
        ["TransactionCategory", "TransactionType", "UtrNo", "TotalTransactionAmount", "EnterpriseName"],
        ["ADD MONEY", "CREDIT", "123456789012", 1000, "Acme Corp"],
        ["OPS ADJUSTMENT", "CREDIT", "RE1998877", 250, "Beta Ltd"],
        ["ADD MONEY", "CREDIT", "TRXV000111", 500, "Excluded Co"],
        ["ADD MONEY", "CREDIT", "555555", 300, "NoBank Co"],
        ["ADD MONEY", "DEBIT", "777777", 400, "WrongType Co"],
        ["ADD MONEY", "CREDIT", "111222", 700, "Mismatch Co"],
    ]
    bank_rows = [
        ["Narrative", "Credit"],
        ["IMPS/123456789012/XYZ/ACME", 1000],
        ["NEFT/998877/SOMEBANK/REF", 250],
        ["~EROUTE~333999~ INEFT desc", 50],
        ["111222 raw digits only narrative", 650],
    ]
    mod = get_module("bank_addmoney")
    ctx = RunContext(
        run_id="test",
        files=[
            UploadedFile(slot="ops", filename="ops.xlsx", content=make_xlsx(ops_rows), size_bytes=1),
            UploadedFile(slot="bank", filename="bank.xlsx", content=make_xlsx(bank_rows), size_bytes=1),
        ],
    )
    parsed = mod.parse(ctx)
    findings = mod.validate(parsed, ctx)
    assert not any(f.level == "err" for f in findings)
    return mod.reconcile(parsed, ctx, findings)


def test_end_to_end_statuses(make_xlsx):
    output = _run(make_xlsx)
    by_utr = {r["Final UTR"]: r for r in output.raw["detail_rows"]}

    assert "TRXV" not in str(list(by_utr.keys()))
    assert by_utr["123456789012"]["Status"] == "MATCHED"
    assert by_utr["998877"]["Status"] == "MATCHED"
    assert by_utr["555555"]["Status"] == "NOT IN BANK"
    assert by_utr["111222"]["Status"] == "AMOUNT MISMATCH"
    assert by_utr["111222"]["Difference"] == 50.0
    assert by_utr["333999"]["Status"] == "NOT IN OPS"
    assert "777777" not in by_utr  # DEBIT type excluded entirely


def test_build_report_produces_valid_workbook(make_xlsx):
    mod = get_module("bank_addmoney")
    output = _run(make_xlsx)
    ctx = RunContext(run_id="test")
    report = mod.build_report(output, ctx)
    assert report[:2] == b"PK"
