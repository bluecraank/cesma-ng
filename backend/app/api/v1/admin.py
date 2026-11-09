"""Super administrator endpoints: users and credential profiles."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CallerDep, Db, csrf_guard, get_secret_box
from app.core.crypto import SecretBox
from app.models import CredentialProfile
from app.schemas import CredentialProfileIn, CredentialProfileOut, UserOut, UserUpdate
from app.services import credentials, users

router = APIRouter(tags=["administration"], dependencies=[Depends(csrf_guard)])

Box = Annotated[SecretBox, Depends(get_secret_box)]


@router.get("/users", response_model=list[UserOut])
async def list_users(db: Db, caller: CallerDep) -> object:
    return await users.list_users(db, caller)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: int, body: UserUpdate, db: Db, caller: CallerDep) -> object:
    return await users.update_user(db, caller, user_id, **body.model_dump(exclude_unset=True))


def _profile_out(profile: CredentialProfile, box: SecretBox) -> CredentialProfileOut:
    out = CredentialProfileOut.model_validate(profile)
    out.secrets_set = credentials.secrets_set(profile, box)
    return out


@router.get("/credential-profiles", response_model=list[CredentialProfileOut])
async def list_profiles(db: Db, caller: CallerDep, box: Box) -> object:
    return [_profile_out(p, box) for p in await credentials.list_profiles(db, caller)]


@router.post(
    "/credential-profiles", response_model=CredentialProfileOut, status_code=status.HTTP_201_CREATED
)
async def create_profile(body: CredentialProfileIn, db: Db, caller: CallerDep, box: Box) -> object:
    profile = await credentials.save_profile(db, caller, box, body.model_dump(exclude_unset=True))
    return _profile_out(profile, box)


@router.put("/credential-profiles/{profile_id}", response_model=CredentialProfileOut)
async def update_profile(
    profile_id: int, body: CredentialProfileIn, db: Db, caller: CallerDep, box: Box
) -> object:
    profile = await credentials.save_profile(
        db, caller, box, body.model_dump(exclude_unset=True), profile_id
    )
    return _profile_out(profile, box)


@router.delete("/credential-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(profile_id: int, db: Db, caller: CallerDep) -> None:
    await credentials.delete_profile(db, caller, profile_id)
