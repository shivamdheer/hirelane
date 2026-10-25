from __future__ import annotations

from hirelane.submit.fields import FormField
from hirelane.submit.plan import Plan
from hirelane.submit.verify import verify

RESUME = "Alex_Rivera_Resume_Fabrikam.pdf"
ALLOWED = "Northwind Analytics Data Analyst Lincoln State University"


def fld(fid: str, label: str, kind: str = "text", value: str = "", required: bool = True,
        options: list[str] | None = None) -> FormField:
    return FormField(fid, label, kind, required, options or [], value)


def good_form() -> tuple[list[FormField], Plan]:
    fields = [fld("f0", "First Name", value="Alex"), fld("f1", "Resume/CV", "file", RESUME),
              fld("f2", "Authorized to work", "select", "Yes", options=["Yes", "No"])]
    plan = Plan(values={"f0": "Alex", "f2": "Yes"}, resume_fid="f1")
    return fields, plan


def run(fields: list[FormField], plan: Plan, **kw: object):
    args = {"resume_file": RESUME, "company": "Fabrikam", "other_companies": ["Contoso", "Adatum Labs"],
            "allowed_text": ALLOWED, "page_errors": []}
    args.update(kw)
    return verify(fields, plan, **args)  # type: ignore[arg-type]


def test_a_correct_form_passes() -> None:
    fields, plan = good_form()
    assert run(fields, plan).ok


def test_wrong_resume_file_fails() -> None:
    fields, plan = good_form()
    fields[1].value = "Alex_Rivera_Resume_Contoso.pdf"
    assert any("resume field shows" in p for p in run(fields, plan).problems)


def test_missing_resume_field_fails() -> None:
    fields, plan = good_form()
    plan.resume_fid = ""
    assert any("no resume upload" in p for p in run(fields[:1] + fields[2:], plan).problems)


def test_required_empty_and_unanswered_fail() -> None:
    fields, plan = good_form()
    fields.append(fld("f3", "Phone"))
    plan.unanswered.append(fld("f4", "Favorite color"))
    problems = run(fields, plan).problems
    assert any("required field empty: Phone" in p for p in problems)
    assert any("no answer for required question: Favorite color" in p for p in problems)


def test_value_that_differs_from_the_plan_fails() -> None:
    fields, plan = good_form()
    fields[0].value = "Alexander"
    assert any("reads 'Alexander'" in p for p in run(fields, plan).problems)


def test_another_companys_name_in_a_field_fails() -> None:
    fields, plan = good_form()
    note = "I would love to join Contoso because of its mission"
    fields.append(fld("f3", "Why us", "textarea", note, required=False))
    assert any("Contoso" in p for p in run(fields, plan).problems)


def test_the_users_own_employers_are_allowed() -> None:
    fields, plan = good_form()
    fields.append(fld("f3", "Current employer", value="Northwind Analytics"))
    assert run(fields, plan, other_companies=["Northwind Analytics"]).ok


def test_placeholder_text_and_page_errors_fail() -> None:
    fields, plan = good_form()
    fields.append(fld("f3", "Notes", "textarea", "lorem ipsum dolor", required=False))
    problems = run(fields, plan, page_errors=["This field is required"]).problems
    assert any("placeholder text" in p for p in problems)
    assert any("page shows" in p for p in problems)


def test_required_unsupported_upload_fails() -> None:
    fields, plan = good_form()
    plan.unsupported.append(fld("f9", "Writing sample", "file"))
    assert any("required upload this tool does not provide" in p for p in run(fields, plan).problems)


def test_an_empty_select_fails_even_when_planned() -> None:
    fields, plan = good_form()
    fields[2].value = ""
    assert any("is empty, expected 'Yes'" in p for p in run(fields, plan).problems)
