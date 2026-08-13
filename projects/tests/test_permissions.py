from projects.permissions import (
    can_change_role,
    can_delete_project,
    can_invite,
    can_leave,
    can_remove,
    can_transfer_ownership,
)


def test_owner_can_manage_but_not_leave_without_transferring():
    assert can_invite("owner")
    assert can_change_role("owner")
    assert can_transfer_ownership("owner")
    assert can_delete_project("owner")
    assert not can_leave("owner")


def test_admin_can_invite_and_leave_but_not_manage_roles_or_delete():
    assert can_invite("admin")
    assert can_leave("admin")
    assert not can_change_role("admin")
    assert not can_transfer_ownership("admin")
    assert not can_delete_project("admin")


def test_member_can_only_leave():
    assert can_leave("member")
    assert not can_invite("member")
    assert not can_change_role("member")
    assert not can_transfer_ownership("member")
    assert not can_delete_project("member")


def test_remove_matrix():
    assert can_remove("owner", "admin")
    assert can_remove("owner", "member")
    assert not can_remove("owner", "owner")
    assert can_remove("admin", "member")
    assert not can_remove("admin", "admin")
    assert not can_remove("admin", "owner")
    assert not can_remove("member", "member")
    assert not can_remove("member", "admin")
