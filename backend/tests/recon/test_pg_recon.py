"""Regression test using the exact 15-row Ops/PayU/Cashfree sample data
shipped inside the original `Reconciliation_Tool.xlsm` - asserts the ported
`DetermineAction` rule engine produces the same action for every row the
VBA macro's own sample data was built to demonstrate.
"""
from app.recon.base import RunContext, UploadedFile
from app.recon.registry import get_module

OPS_ROWS = [
    ["Transaction ID", "Customer Name", "Amount (INR)", "Date & Time", "Status", "Payment Mode", "Remarks"],
    ["TRX1001", "Arjun Sharma", 1500, "01-Jun-24 09:15", "COMPLETED", "UPI", ""],
    ["TRX1002", "Priya Mehta", 800, "01-Jun-24 09:42", "FAILED", "NetBanking", "Bank timeout"],
    ["TRX1003", "Rohan Das", 2200, "01-Jun-24 10:05", "FAILED", "Card", ""],
    ["TRX1004", "Sneha Kapoor", 500, "01-Jun-24 10:30", "CANCELED", "UPI", "User cancelled"],
    ["TRX1005", "Vikram Singh", 3000, "01-Jun-24 11:00", "COMPLETED", "Wallet", ""],
    ["TRX1006", "Anjali Rao", 1200, "01-Jun-24 11:25", "FAILED", "Card", "OTP failed"],
    ["TRX1007", "Karthik Nair", 4500, "01-Jun-24 12:00", "MANUAL", "NetBanking", "Manual review"],
    ["TRX1008", "Deepa Joshi", 700, "01-Jun-24 12:30", "FAILED", "UPI", ""],
    ["TRX1009", "Suresh Pillai", 950, "01-Jun-24 13:00", "CANCELED", "Card", ""],
    ["TRX1010", "Meena Reddy", 1800, "01-Jun-24 13:30", "INITIATED", "UPI", "Pending"],
    ["TRX1011", "Abhishek Gupta", 2500, "01-Jun-24 14:00", "COMPLETED", "NetBanking", ""],
    ["TRX1012", "Pooja Iyer", 600, "01-Jun-24 14:30", "EXCEPTION", "Card", "System error"],
    ["TRX1013", "Rahul Verma", 3300, "01-Jun-24 15:00", "COMPLETED", "UPI", ""],
    ["TRX1014", "Nisha Agarwal", 420, "01-Jun-24 15:30", "FAILED", "Wallet", "Insufficient bal."],
    ["TRX1015", "Manoj Kumar", 1100, "01-Jun-24 16:00", "CANCELED", "NetBanking", ""],
]
PAYU_ROWS = [
    ["txnid", "mihpayid", "amount", "txndate", "status", "bank_ref_num", "error_code", "error_message"],
    ["TRX1001", "PAY-9001", 1500, "01-Jun-24", "captured", "ICICI-8812", "", ""],
    ["TRX1002", "PAY-9002", 800, "01-Jun-24", "failed", "", "E501", "Bank declined"],
    ["TRX1003", "PAY-9003", 2200, "01-Jun-24", "dropped", "", "E502", "Connection dropped"],
    ["TRX1006", "PAY-9006", 1200, "01-Jun-24", "userCancelled", "", "", ""],
    ["TRX1007", "PAY-9007", 4500, "01-Jun-24", "captured", "HDFC-4421", "", ""],
    ["TRX1008", "PAY-9008", 700, "01-Jun-24", "failed", "", "E503", "Timeout"],
    ["TRX1011", "PAY-9011", 2500, "01-Jun-24", "captured", "SBI-7732", "", ""],
    ["TRX1012", "PAY-9012", 600, "01-Jun-24", "captured", "AXIS-3341", "", ""],
    ["TRX1013", "PAY-9013", 3300, "01-Jun-24", "captured", "ICICI-9954", "", ""],
    ["TRX1014", "PAY-9014", 420, "01-Jun-24", "failed", "", "E504", "Low balance"],
    ["TRX1016", "PAY-9016", 999, "01-Jun-24", "captured", "HDFC-5512", "", ""],
]
CASHFREE_ROWS = [
    ["Order Id", "cf_payment_id", "Order Amount", "Payment Time", "Transaction Status", "Payment Mode", "Bank Reference", "Failure Reason"],
    ["TRX1001", "CF-5001", 1500, "01-Jun-24 09:16", "SUCCESS", "UPI", "UPI-BB1221", ""],
    ["TRX1004", "CF-5004", 500, "01-Jun-24 10:31", "FAILED", "UPI", "", "User cancelled"],
    ["TRX1005", "CF-5005", 3000, "01-Jun-24 11:01", "SUCCESS", "Wallet", "WAL-7731", ""],
    ["TRX1007", "CF-5007", 4500, "01-Jun-24 12:01", "SUCCESS", "NetBanking", "NB-3342", ""],
    ["TRX1009", "CF-5009", 950, "01-Jun-24 13:01", "FAILED", "Card", "", "Declined"],
    ["TRX1010", "CF-5010", 1800, "01-Jun-24 13:31", "SUCCESS", "UPI", "UPI-9934", ""],
    ["TRX1011", "CF-5011", 2500, "01-Jun-24 14:01", "SUCCESS", "NetBanking", "NB-8812", ""],
    ["TRX1012", "CF-5012", 600, "01-Jun-24 14:31", "SUCCESS", "Card", "CARD-4421", ""],
    ["TRX1013", "CF-5013", 3300, "01-Jun-24 15:01", "SUCCESS", "UPI", "UPI-6654", ""],
    ["TRX1015", "CF-5015", 1100, "01-Jun-24 16:01", "FAILED", "NetBanking", "", "Bank error"],
    ["TRX1017", "CF-5017", 2750, "01-Jun-24 16:30", "SUCCESS", "Card", "CARD-9987", ""],
]

EXPECTED_ACTIONS = {
    "TRX1001": "Successfully Completed",
    "TRX1002": "Failed",
    "TRX1003": "Failed",
    "TRX1004": "Failed",
    "TRX1005": "Successfully Completed",
    "TRX1006": "Failed",
    "TRX1007": "To Check",
    "TRX1008": "Failed",
    "TRX1009": "Failed",
    "TRX1010": "To Check",
    "TRX1011": "Successfully Completed",
    "TRX1012": "To Check",
    "TRX1013": "Successfully Completed",
    "TRX1014": "Failed",
    "TRX1015": "Failed",
    "TRX1016": "Manual Check Required",  # PayU-only orphan
    "TRX1017": "Manual Check Required",  # Cashfree-only orphan
}


def _run(make_xlsx):
    mod = get_module("pg_recon")
    ctx = RunContext(
        run_id="test",
        files=[
            UploadedFile(slot="ops", filename="ops.xlsx", content=make_xlsx(OPS_ROWS), size_bytes=1),
            UploadedFile(slot="payu", filename="payu.xlsx", content=make_xlsx(PAYU_ROWS), size_bytes=1),
            UploadedFile(slot="cashfree", filename="cf.xlsx", content=make_xlsx(CASHFREE_ROWS), size_bytes=1),
        ],
    )
    parsed = mod.parse(ctx)
    findings = mod.validate(parsed, ctx)
    assert not any(f.level == "err" for f in findings)
    return mod.reconcile(parsed, ctx, findings)


def test_action_matches_vba_rule_engine_for_every_sample_row(make_xlsx):
    output = _run(make_xlsx)
    by_key = {r["Transaction ID"]: r["Action Point"] for r in output.raw["detail_rows"]}
    for key, expected in EXPECTED_ACTIONS.items():
        assert by_key[key] == expected, f"{key}: expected {expected}, got {by_key[key]}"


def test_coverage_tagging_and_orphan_passes(make_xlsx):
    output = _run(make_xlsx)
    by_key = {r["Transaction ID"]: r for r in output.raw["detail_rows"]}
    assert by_key["TRX1016"]["Source Coverage"] == "PayU only"
    assert by_key["TRX1017"]["Source Coverage"] == "CF only"
    assert by_key["TRX1001"]["Source Coverage"] == "Ops + PayU + CF"


def test_build_report_produces_valid_workbook(make_xlsx):
    mod = get_module("pg_recon")
    output = _run(make_xlsx)
    ctx = RunContext(run_id="test")
    report = mod.build_report(output, ctx)
    assert report[:2] == b"PK"
    assert len(report) > 1000
