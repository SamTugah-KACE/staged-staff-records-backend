import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ..Crud.user_base import UserCRUD
from unittest.mock import AsyncMock

@pytest.fixture
def mock_db():
    return AsyncMock(spec=AsyncSession)

@pytest.fixture
def user_crud(mock_user_model, mock_role_model, mock_org_model, mock_employee_model, mock_audit_model):
    return UserCRUD(
        user_model=mock_user_model,
        role_model=mock_role_model,
        org_model=mock_org_model,
        employee_model=mock_employee_model,
        audit_model=mock_audit_model
    )

@pytest.mark.asyncio
async def test_create_ceo_account_success(mock_db, user_crud, mock_organization_data):
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    result = await user_crud.create_ceo_account(mock_db, mock_organization_data, AsyncMock())
    assert result["message"] == "CEO account created successfully."

@pytest.mark.asyncio
async def test_create_ceo_account_duplicate(mock_db, user_crud, mock_organization_data):
    mock_db.query.return_value.filter.return_value.first.return_value = mock_organization_data
    with pytest.raises(HTTPException) as exc:
        await user_crud.create_ceo_account(mock_db, mock_organization_data, AsyncMock())
    assert exc.value.status_code == 400
