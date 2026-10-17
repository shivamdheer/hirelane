from __future__ import annotations

from pathlib import Path

import pytest

from hirelane.companies import CompaniesError, Company, add_company, load_companies, save_companies


def test_companies_file_roundtrip_and_validation(tmp_path: Path) -> None:
    path = tmp_path / "companies.yaml"
    assert add_company(Company("Fabrikam", "greenhouse", "fabrikam"), path)
    assert not add_company(Company("Fabrikam again", "greenhouse", "fabrikam"), path)
    save_companies([*load_companies(path), Company("Contoso", "lever", "contoso")], path)
    assert [c.slug for c in load_companies(path)] == ["fabrikam", "contoso"]
    with pytest.raises(CompaniesError):
        add_company(Company("X", "workday", "x"), path)
    with pytest.raises(CompaniesError):
        add_company(Company("X", "lever", "bad slug!"), path)
